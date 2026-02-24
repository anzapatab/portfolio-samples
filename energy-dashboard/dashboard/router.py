# -*- coding: utf-8 -*-
"""
Multi-page router callback.

Maps URL pathnames to page layouts for client-side navigation.
Supports 11 analytical views plus authentication.
"""
from __future__ import annotations
from dash import Input, Output, callback
from ..pages import (
    overview,
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
    login,
)


@callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
)
def _router(pathname: str):
    # Login page (always accessible)
    if pathname == "/login":
        return login.layout()

    # Main pages
    if pathname in ("/", "/overview", None):
        return overview.layout
    if pathname == "/explorer":
        return explorer.layout
    if pathname == "/temporal-patterns":
        return temporal_patterns.layout
    if pathname == "/scenarios-runs":
        return scenarios_runs.layout
    if pathname == "/spreads-congestion":
        return spreads_congestion.layout
    if pathname == "/risk-distribution":
        return risk_distribution.layout
    if pathname == "/correlations-clustering":
        return correlations_clustering.layout
    if pathname == "/map":
        return map.layout
    if pathname == "/events-anomalies":
        return events_anomalies.layout
    if pathname == "/data-health":
        return data_health.layout
    if pathname == "/north-center-analysis":
        return north_center_analysis.layout

    return overview.layout
