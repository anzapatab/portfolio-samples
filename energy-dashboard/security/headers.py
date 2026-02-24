# src/dashboard/auth/security/headers.py
# -*- coding: utf-8 -*-
"""
Security headers middleware.

Implements OWASP security headers:
- Content-Security-Policy (CSP)
- Strict-Transport-Security (HSTS)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- Cache-Control for sensitive data
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from flask import Flask, Response

logger = logging.getLogger(__name__)


def build_csp_header(config: dict) -> str:
    """
    Build Content-Security-Policy header.

    Configured for Dash/Plotly applications.
    """
    # Base CSP directives for Dash applications
    directives = {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "'unsafe-inline'",  # Required for Dash callbacks
            "'unsafe-eval'",    # Required for Plotly
            "https://cdn.plot.ly",
            "https://cdn.jsdelivr.net",
        ],
        "style-src": [
            "'self'",
            "'unsafe-inline'",  # Required for Dash/Plotly inline styles
            "https://fonts.googleapis.com",
            "https://cdn.jsdelivr.net",
        ],
        "font-src": [
            "'self'",
            "https://fonts.gstatic.com",
            "data:",
        ],
        "img-src": [
            "'self'",
            "data:",
            "blob:",
            "https:",
        ],
        "connect-src": [
            "'self'",
            "https://api.pwnedpasswords.com",  # For breach checking
        ],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "upgrade-insecure-requests": [],
    }

    # Build header string
    parts = []
    for directive, values in directives.items():
        if values:
            parts.append(f"{directive} {' '.join(values)}")
        else:
            parts.append(directive)

    return "; ".join(parts)


def build_permissions_policy(config: dict) -> str:
    """
    Build Permissions-Policy header.

    Restricts browser features that aren't needed.
    """
    # Disable unnecessary features
    policies = {
        "accelerometer": "()",
        "ambient-light-sensor": "()",
        "autoplay": "()",
        "battery": "()",
        "camera": "()",
        "display-capture": "()",
        "document-domain": "()",
        "encrypted-media": "()",
        "fullscreen": "(self)",
        "geolocation": "()",
        "gyroscope": "()",
        "layout-animations": "(self)",
        "legacy-image-formats": "(self)",
        "magnetometer": "()",
        "microphone": "()",
        "midi": "()",
        "oversized-images": "(self)",
        "payment": "()",
        "picture-in-picture": "()",
        "publickey-credentials-get": "()",
        "speaker-selection": "()",
        "sync-xhr": "(self)",
        "unoptimized-images": "(self)",
        "unsized-media": "(self)",
        "usb": "()",
        "screen-wake-lock": "()",
        "web-share": "()",
        "xr-spatial-tracking": "()",
    }

    return ", ".join(f"{k}={v}" for k, v in policies.items())


def init_security_headers(flask_app: Flask, config: dict) -> None:
    """
    Initialize security headers middleware.

    Adds security headers to all responses.
    """

    @flask_app.after_request
    def add_security_headers(response: Response) -> Response:
        """Add security headers to response."""

        # Strict-Transport-Security (HSTS)
        if config.get("hsts", True):
            max_age = config.get("hsts_max_age", 31536000)
            hsts_value = f"max-age={max_age}; includeSubDomains"
            if config.get("hsts_preload", False):
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Content-Security-Policy
        if config.get("content_security_policy", True):
            csp = build_csp_header(config)
            response.headers["Content-Security-Policy"] = csp

        # X-Frame-Options
        x_frame = config.get("x_frame_options", "DENY")
        if x_frame:
            response.headers["X-Frame-Options"] = x_frame

        # X-Content-Type-Options
        if config.get("x_content_type_options", True):
            response.headers["X-Content-Type-Options"] = "nosniff"

        # X-XSS-Protection (legacy but still useful)
        if config.get("x_xss_protection", True):
            response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy
        referrer = config.get("referrer_policy", "strict-origin-when-cross-origin")
        if referrer:
            response.headers["Referrer-Policy"] = referrer

        # Permissions-Policy
        if config.get("permissions_policy", True):
            response.headers["Permissions-Policy"] = build_permissions_policy(config)

        # Cache-Control for sensitive pages
        if _is_sensitive_path(response):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # Remove potentially dangerous headers
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response

    logger.info("Security headers middleware configured")


def _is_sensitive_path(response) -> bool:
    """
    Determine if the response is for a sensitive path.

    Sensitive paths should not be cached.
    """
    from flask import request

    sensitive_paths = [
        "/login",
        "/logout",
        "/auth/",
        "/admin/",
        "/api/",
    ]

    path = request.path.lower()
    return any(path.startswith(p) for p in sensitive_paths)


def get_security_headers_report() -> Dict[str, str]:
    """
    Generate a report of current security headers.

    Useful for security audits.
    """
    return {
        "Strict-Transport-Security": "Enabled (1 year, includeSubDomains)",
        "Content-Security-Policy": "Configured for Dash/Plotly",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "Restrictive (most features disabled)",
        "Cache-Control": "no-store for sensitive paths",
    }
