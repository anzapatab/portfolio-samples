# src/dashboard/app.py
# -*- coding: utf-8 -*-
"""
Dash application factory.

Creates and configures the multi-page Dash application with:
- Prometheus metrics middleware
- Optional authentication with enterprise security
- Health/readiness endpoints
- Background data preloading
- Multi-page validation layout
"""
from __future__ import annotations

from pathlib import Path
from dash import Dash
from flask import jsonify
import os
import logging

from services.config_loader import setup_logging, load_yaml
from services.data_preloader import preload_status
from services.filters_loader import filters_health
from dashboard.constants import DATA_ROOT
from services.smart_cache import cache_stats
from services.metrics import (
    metrics_middleware,
    get_metrics_response,
    update_data_root_status,
    update_arrow_files_count,
    update_preload_status,
    update_filter_rows,
    update_cache_metrics,
    set_app_info,
    PROMETHEUS_AVAILABLE,
)

def _coerce_bool(x) -> bool:
    if x is None:
        return False
    return str(x).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def create_app(*, debug: bool | None = None, devtools: bool | None = None) -> Dash:
    """
    Create the main Dash application instance.

    Parameters
    ----------
    debug : bool | None
        Force debug mode (verbose logs, no route silencing).
        If None, reads from APP_DEBUG env var (default False).
    devtools : bool | None
        Activate Dash devtools/hot-reload UI (for development).
        If None, reads from APP_DEVTOOLS env var (default False).
    """
    # ======== Logging ========
    setup_logging()
    logger = logging.getLogger(__name__)

    # ======== Flags from environment (fallbacks) ========
    env_debug = _coerce_bool(os.getenv("APP_DEBUG"))
    env_devtools = _coerce_bool(os.getenv("APP_DEVTOOLS"))
    debug = env_debug if debug is None else bool(debug)
    devtools = env_devtools if devtools is None else bool(devtools)

    app = Dash(
        __name__,
        title="Energy Market Dashboard",
        assets_folder=str((Path(__file__).resolve().parent / "assets")),
        update_title=None,
        # IMPORTANT: suppress_callback_exceptions=True is REQUIRED for multi-page apps
        # because callbacks are registered at startup but page components only exist
        # when navigated to. Without this, Dash raises exceptions when validating
        # callbacks against the initial layout (which doesn't include page-specific components).
        # See: https://dash.plotly.com/urls#dynamically-create-a-layout-for-multi-page-app-validation
        suppress_callback_exceptions=True,
    )

    # Store flags so any callback can read them via Flask
    app.server.config.update(
        APP_DEBUG=debug,
        APP_DEVTOOLS=devtools,
    )

    # ======== Prometheus Metrics Middleware ========
    metrics_middleware(app.server)
    set_app_info(version="1.1.0")

    # ======== Authentication (optional) ========
    app_cfg = load_yaml("config/app.yaml")
    auth_cfg = app_cfg.get("auth", {})

    if auth_cfg.get("enabled", False):
        from dashboard.auth import init_auth
        init_auth(app, auth_cfg)
        logger.info("Authentication enabled")

    # Optional: fine-tune dev tools (without breaking production)
    try:
        app.enable_dev_tools(
            dev_tools_ui=devtools,
            dev_tools_hot_reload=devtools,
            dev_tools_silence_routes_logging=not debug,
            dev_tools_serve_dev_bundles=devtools,
        )
    except Exception as exc:
        # Old Dash version or production environment: silently ignore
        logger.debug("Could not activate dev tools: %s", exc, exc_info=True)

    # ======== Layout and router ========
    from .layout import serve_layout
    from dash import html

    app.layout = serve_layout

    # ======== Validation Layout (for multi-page apps) ========
    # Includes all component IDs from all pages to avoid client-side
    # validation errors when callbacks reference components that don't
    # exist on the current page.
    # See: https://dash.plotly.com/urls#dynamically-create-a-layout-for-multi-page-app-validation
    from .pages import (
        north_center_analysis as nc_page,
        explorer as explorer_page,
        temporal_patterns as tp_page,
        scenarios_runs as sr_page,
        spreads_congestion as sc_page,
        risk_distribution as rd_page,
        correlations_clustering as cc_page,
        map as map_page,
        events_anomalies as ev_page,
        data_health as dh_page,
    )
    from .callbacks.overview.layout import layout as overview_layout_fn

    app.validation_layout = html.Div([
        serve_layout(),                  # Main layout
        overview_layout_fn(),            # Overview components (is a function)
        nc_page.layout,                  # North-Center Analysis components
        explorer_page.layout,            # Explorer components
        tp_page.layout,                  # Temporal Patterns components
        sr_page.layout,                  # Scenarios Runs components
        sc_page.layout,                  # Spreads Congestion components
        rd_page.layout,                  # Risk Distribution components
        cc_page.layout,                  # Correlations Clustering components
        map_page.layout,                 # Map components
        ev_page.layout,                  # Events Anomalies components
        dh_page.layout,                  # Data Health components
    ])

    # ======== Import side-effects ========
    from .callbacks import (  # noqa: F401
        router,
        explorer,
        temporal_patterns,
        scenarios_runs,
        spreads_congestion,
        risk_distribution,
        correlations_clustering,
        map,
        events_anomalies,
        data_health,
        north_center_analysis,
        theme,
        filters,
        auth as auth_callbacks,
    )

    # ======== Register per-tab callbacks explicitly ========
    from .callbacks import overview as cb_overview

    cb_overview.register_callbacks(app)

    def _try_register(mod):
        fn = getattr(mod, "register_callbacks", None)
        if callable(fn):
            fn(app)

    for mod in (
        explorer,
        temporal_patterns,
        scenarios_runs,
        spreads_congestion,
        risk_distribution,
        correlations_clustering,
        map,
        events_anomalies,
        data_health,
        north_center_analysis,
    ):
        _try_register(mod)

    # ======== Presets (clientside) ========
    from .callbacks import presets

    presets.register_callbacks(app)

    # ======== Optional diagnostics ========
    if debug:
        for k in app.callback_map.keys():
            if "run-id.value" in k:
                logger.debug("[CALLBACK using run-id]: %s", k)

    # ======== Health endpoints ========
    _max_arrow_files = int(os.getenv("HEALTH_MAX_ARROW", "2000"))
    _skip_arrow_count = os.getenv("SKIP_ARROW_COUNT", "0").strip().lower() in {"1", "true", "yes", "on"}
    _arrow_count_file = os.getenv("ARROW_COUNT_FILE")
    _asset_root = Path(__file__).resolve().parent / "assets"

    def _count_arrow_files(max_files: int) -> dict:
        """
        Count .arrow files with limit to avoid walking huge trees.
        Returns {"count": int | None, "truncated": bool, "source": str}.
        - Uses pre-computed file if ARROW_COUNT_FILE is set.
        - If SKIP_ARROW_COUNT is active, skips disk traversal.
        """
        info = {"count": None, "truncated": False, "source": "scan"}
        if _skip_arrow_count:
            info["source"] = "skipped"
            info["truncated"] = True
            return info

        if _arrow_count_file:
            try:
                path = Path(_arrow_count_file)
                if not path.is_absolute():
                    path = DATA_ROOT / path
                val = int(path.read_text().strip())
                info["count"] = val
                info["source"] = "file"
                return info
            except Exception as exc:
                logger.warning("Could not read ARROW_COUNT_FILE=%s: %s", _arrow_count_file, exc, exc_info=True)

        if not DATA_ROOT.exists():
            return info
        try:
            count = 0
            for _ in DATA_ROOT.rglob("*.arrow"):
                count += 1
                if count > max_files:
                    info["truncated"] = True
                    break
            info["count"] = min(count, max_files)
        except Exception as exc:
            logger.warning("Could not count .arrow files in %s: %s", DATA_ROOT, exc, exc_info=True)
        return info

    def _assets_health() -> dict:
        required = {
            "toast.css": (_asset_root / "toast.css"),
            "toast.js": (_asset_root / "toast.js"),
        }
        missing = [name for name, path in required.items() if not path.exists()]
        return {
            "missing": missing,
            "ok": len(missing) == 0,
        }

    @app.server.route("/healthz", methods=["GET"])
    def _healthz():
        status = preload_status()
        caches = cache_stats()
        filters = filters_health()
        arrow_count = _count_arrow_files(_max_arrow_files)
        assets = _assets_health()

        return jsonify({
            "status": "ok",
            "data_root": str(DATA_ROOT),
            "data_root_exists": DATA_ROOT.exists(),
            "arrow_files": arrow_count,
            "preload": status,
            "cache": caches,
            "filters": filters,
            "assets": assets,
        })

    @app.server.route("/metrics", methods=["GET"])
    def _metrics():
        """
        Prometheus metrics endpoint.

        Uses prometheus_client library for proper metric formatting.
        Updates application-specific gauges before returning.
        """
        # Update application metrics before generating response
        caches = cache_stats()
        filters = filters_health()
        arrow_count = _count_arrow_files(_max_arrow_files)

        # Update Prometheus gauges
        update_data_root_status(DATA_ROOT.exists())

        if arrow_count["count"] is not None:
            update_arrow_files_count(arrow_count["count"])

        # Update filter row counts
        for catalog in ("scenarios", "hydrology", "nodes"):
            rows = filters.get(catalog, {}).get("rows", 0)
            update_filter_rows(catalog, rows)

        # Update cache metrics
        for cache_name, stats in caches.items():
            update_cache_metrics(cache_name, stats)

        # Update preload status
        status = preload_status()
        for key in ("scenarios_loaded", "hydrology_loaded", "nodes_loaded", "geo_loaded"):
            data_type = key.replace("_loaded", "")
            update_preload_status(data_type, status.get(key, False))

        # Generate prometheus_client response
        content, status_code, headers = get_metrics_response()
        return content, status_code, headers

    # ======== Background data preloading ========
    # Preload in background to reduce first-load latency
    try:
        # 1. Geographic data (map)
        from .callbacks.map import start_preload_thread as start_geo_preload
        start_geo_preload()

        # 2. Filter data (scenarios, hydrology, nodes)
        from services.data_preloader import start_preload_thread as start_filters_preload
        start_filters_preload()

    except Exception as e:
        logger.warning("Could not start data preload: %s", e, exc_info=True)

    return app
