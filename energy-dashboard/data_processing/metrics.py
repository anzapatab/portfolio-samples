# -*- coding: utf-8 -*-
"""
Prometheus metrics service for the Energy Market Dashboard.

This module provides:
- HTTP request metrics (latency, count, errors)
- Application-specific metrics (cache, data loading)
- Flask middleware for automatic request instrumentation
"""
from __future__ import annotations

import time
import logging
from functools import wraps
from typing import Callable, Any

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        multiprocess,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================
# Metrics Registry
# ============================================================

# Use default registry (works with gunicorn --workers)
# For multiprocess mode, set prometheus_multiproc_dir env var

def _get_registry() -> Any:
    """Get the appropriate registry for the environment."""
    return REGISTRY


# ============================================================
# HTTP Request Metrics
# ============================================================

if PROMETHEUS_AVAILABLE:
    # Request counter
    HTTP_REQUESTS_TOTAL = Counter(
        "app_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
    )

    # Request latency histogram
    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "app_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    # Active requests gauge
    HTTP_REQUESTS_IN_PROGRESS = Gauge(
        "app_http_requests_in_progress",
        "Number of HTTP requests currently being processed",
        ["method"],
    )

    # ============================================================
    # Application Metrics
    # ============================================================

    # Cache metrics
    CACHE_HITS = Counter(
        "app_cache_hits_total",
        "Cache hits",
        ["cache_name", "cache_type"],  # cache_type: memory, disk
    )

    CACHE_MISSES = Counter(
        "app_cache_misses_total",
        "Cache misses",
        ["cache_name"],
    )

    CACHE_SIZE = Gauge(
        "app_cache_size_bytes",
        "Current cache size in bytes",
        ["cache_name", "cache_type"],
    )

    CACHE_ITEMS = Gauge(
        "app_cache_items",
        "Number of items in cache",
        ["cache_name", "cache_type"],
    )

    # Data loading metrics
    DATA_LOAD_DURATION = Histogram(
        "app_data_load_duration_seconds",
        "Time to load data",
        ["data_type"],
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )

    DATA_ROWS_LOADED = Counter(
        "app_data_rows_loaded_total",
        "Total rows loaded from data sources",
        ["data_type"],
    )

    # Arrow files gauge
    ARROW_FILES_TOTAL = Gauge(
        "app_arrow_files_total",
        "Number of Arrow files in DATA_ROOT",
    )

    # Data root status
    DATA_ROOT_EXISTS = Gauge(
        "app_data_root_exists",
        "Whether DATA_ROOT directory exists (1=yes, 0=no)",
    )

    # Preload status
    PRELOAD_COMPLETE = Gauge(
        "app_preload_complete",
        "Whether data preload is complete (1=yes, 0=no)",
        ["data_type"],
    )

    # Filter catalog rows
    FILTER_ROWS = Gauge(
        "app_filter_rows",
        "Number of rows in filter catalogs",
        ["catalog"],
    )

    # Application info
    APP_INFO = Gauge(
        "app_info",
        "Application information",
        ["version"],
    )


# ============================================================
# Flask Middleware
# ============================================================

def metrics_middleware(app):
    """
    Add Prometheus metrics middleware to a Flask app.

    Usage:
        from services.metrics import metrics_middleware
        metrics_middleware(app.server)
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("prometheus_client not installed, metrics disabled")
        return

    @app.before_request
    def _before_request():
        from flask import request, g
        g.start_time = time.perf_counter()
        HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).inc()

    @app.after_request
    def _after_request(response):
        from flask import request, g

        # Calculate duration
        duration = time.perf_counter() - getattr(g, "start_time", time.perf_counter())

        # Normalize endpoint (avoid cardinality explosion)
        endpoint = _normalize_endpoint(request.path)

        # Record metrics
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
        ).inc()

        HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).dec()

        return response

    logger.info("Prometheus metrics middleware enabled")


def _normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint path to avoid label cardinality explosion.

    Groups dynamic paths like /page/abc into /page/{id}
    """
    # Known static endpoints
    static_endpoints = {
        "/", "/healthz", "/metrics", "/_dash-layout",
        "/_dash-dependencies", "/_dash-update-component",
        "/_reload-hash", "/_alive",
    }

    if path in static_endpoints:
        return path

    # Dash assets
    if path.startswith("/_dash-component-suites/"):
        return "/_dash-component-suites/{...}"
    if path.startswith("/assets/"):
        return "/assets/{...}"

    # Dash callbacks
    if path.startswith("/_dash"):
        return "/_dash/{...}"

    return path


# ============================================================
# Metrics Endpoint Helper
# ============================================================

def get_metrics_response():
    """
    Generate Prometheus metrics response.

    Returns:
        tuple: (content, status_code, headers)
    """
    if not PROMETHEUS_AVAILABLE:
        return "# prometheus_client not installed\n", 200, {"Content-Type": "text/plain"}

    return (
        generate_latest(_get_registry()),
        200,
        {"Content-Type": CONTENT_TYPE_LATEST},
    )


# ============================================================
# Metric Update Functions
# ============================================================

def update_cache_metrics(cache_name: str, stats: dict):
    """Update cache metrics from SmartCache stats."""
    if not PROMETHEUS_AVAILABLE:
        return

    # Memory stats
    CACHE_ITEMS.labels(cache_name=cache_name, cache_type="memory").set(
        stats.get("memory_items", 0)
    )
    CACHE_SIZE.labels(cache_name=cache_name, cache_type="memory").set(
        stats.get("memory_bytes", 0)
    )

    # Disk stats
    CACHE_ITEMS.labels(cache_name=cache_name, cache_type="disk").set(
        stats.get("disk_items", 0)
    )
    CACHE_SIZE.labels(cache_name=cache_name, cache_type="disk").set(
        stats.get("disk_bytes", 0)
    )


def record_cache_hit(cache_name: str, cache_type: str = "memory"):
    """Record a cache hit."""
    if PROMETHEUS_AVAILABLE:
        CACHE_HITS.labels(cache_name=cache_name, cache_type=cache_type).inc()


def record_cache_miss(cache_name: str):
    """Record a cache miss."""
    if PROMETHEUS_AVAILABLE:
        CACHE_MISSES.labels(cache_name=cache_name).inc()


def record_data_load(data_type: str, duration: float, rows: int = 0):
    """Record data loading metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    DATA_LOAD_DURATION.labels(data_type=data_type).observe(duration)
    if rows > 0:
        DATA_ROWS_LOADED.labels(data_type=data_type).inc(rows)


def update_arrow_files_count(count: int):
    """Update Arrow files count gauge."""
    if PROMETHEUS_AVAILABLE:
        ARROW_FILES_TOTAL.set(count)


def update_data_root_status(exists: bool):
    """Update DATA_ROOT exists gauge."""
    if PROMETHEUS_AVAILABLE:
        DATA_ROOT_EXISTS.set(1 if exists else 0)


def update_preload_status(data_type: str, complete: bool):
    """Update preload completion status."""
    if PROMETHEUS_AVAILABLE:
        PRELOAD_COMPLETE.labels(data_type=data_type).set(1 if complete else 0)


def update_filter_rows(catalog: str, rows: int):
    """Update filter catalog row counts."""
    if PROMETHEUS_AVAILABLE:
        FILTER_ROWS.labels(catalog=catalog).set(rows)


def set_app_info(version: str = "1.1.0"):
    """Set application info metric."""
    if PROMETHEUS_AVAILABLE:
        APP_INFO.labels(version=version).set(1)


# ============================================================
# Timing Decorator
# ============================================================

def timed(metric_name: str = "operation"):
    """
    Decorator to time function execution and record to histogram.

    Usage:
        @timed("data_load")
        def load_prices():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not PROMETHEUS_AVAILABLE:
                return func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                DATA_LOAD_DURATION.labels(data_type=metric_name).observe(duration)
        return wrapper
    return decorator
