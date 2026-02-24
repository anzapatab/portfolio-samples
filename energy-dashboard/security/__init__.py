# src/dashboard/auth/security/__init__.py
# -*- coding: utf-8 -*-
"""
Enterprise-grade security module for the Energy Market Dashboard.

Implements OWASP Top 10 protections and industry best practices:
- Rate limiting & brute force protection
- Account lockout mechanisms
- Strong password policies
- Security headers (CSP, HSTS, X-Frame-Options)
- CSRF protection
- Session security & rotation
- Two-factor authentication (TOTP)
- IP-based protection & geofencing
- Comprehensive audit logging
- Argon2id password hashing
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# Security configuration defaults
DEFAULT_SECURITY_CONFIG = {
    # Rate limiting
    "rate_limit": {
        "enabled": True,
        "login_attempts": "5 per minute",
        "api_requests": "100 per minute",
        "global_requests": "1000 per minute",
        "storage": "memory",  # or "redis://localhost:6379"
    },

    # Account lockout
    "lockout": {
        "enabled": True,
        "max_failed_attempts": 5,
        "lockout_duration_minutes": 30,
        "progressive_lockout": True,  # Increases with repeated lockouts
    },

    # Password policy
    "password_policy": {
        "min_length": 12,
        "max_length": 128,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_digit": True,
        "require_special": True,
        "special_chars": "!@#$%^&*()_+-=[]{}|;:,.<>?",
        "prevent_common": True,
        "prevent_user_info": True,
        "history_count": 5,  # Prevent reuse of last N passwords
    },

    # Security headers
    "headers": {
        "enabled": True,
        "hsts": True,
        "hsts_max_age": 31536000,  # 1 year
        "content_security_policy": True,
        "x_frame_options": "DENY",
        "x_content_type_options": True,
        "x_xss_protection": True,
        "referrer_policy": "strict-origin-when-cross-origin",
        "permissions_policy": True,
    },

    # Session security
    "session": {
        "secure_cookie": True,  # HTTPS only
        "httponly": True,
        "samesite": "Lax",
        "rotation_on_login": True,
        "absolute_timeout_hours": 24,
        "idle_timeout_minutes": 60,
        "max_concurrent_sessions": 3,
    },

    # Two-factor authentication
    "totp": {
        "enabled": True,
        "issuer": "Energy Dashboard",
        "digits": 6,
        "interval": 30,
        "algorithm": "SHA1",
        "valid_window": 1,  # Accept codes +/-1 interval
        "enforce_for_admin": True,
    },

    # IP protection
    "ip_protection": {
        "enabled": True,
        "whitelist": [],
        "blacklist": [],
        "block_tor_exit_nodes": False,
        "geo_whitelist": [],  # Empty = allow all
        "geo_blacklist": [],
        "track_suspicious": True,
    },

    # Audit logging
    "audit": {
        "enabled": True,
        "log_successful_logins": True,
        "log_failed_logins": True,
        "log_password_changes": True,
        "log_permission_changes": True,
        "log_admin_actions": True,
        "log_suspicious_activity": True,
        "retention_days": 90,
    },
}


def init_security(flask_app: Flask, security_cfg: dict) -> None:
    """
    Initialize all security modules.

    Called after Flask app is created to configure security features.
    """
    from .rate_limiter import init_rate_limiter
    from .headers import init_security_headers
    from .session import init_session_security
    from .audit_logger import init_audit_logger
    from .ip_protection import init_ip_protection
    from .csrf import init_csrf_protection

    # Merge with defaults
    config = {**DEFAULT_SECURITY_CONFIG, **security_cfg}

    # Store config in app
    flask_app.config["SECURITY_CONFIG"] = config

    # Initialize modules
    if config.get("rate_limit", {}).get("enabled", True):
        init_rate_limiter(flask_app, config["rate_limit"])
        logger.info("Rate limiter initialized")

    if config.get("headers", {}).get("enabled", True):
        init_security_headers(flask_app, config["headers"])
        logger.info("Security headers initialized")

    if config.get("session", {}):
        init_session_security(flask_app, config["session"])
        logger.info("Session security initialized")

    if config.get("audit", {}).get("enabled", True):
        init_audit_logger(flask_app, config["audit"])
        logger.info("Audit logging initialized")

    if config.get("ip_protection", {}).get("enabled", True):
        init_ip_protection(flask_app, config["ip_protection"])
        logger.info("IP protection initialized")

    init_csrf_protection(flask_app)
    logger.info("CSRF protection initialized")

    logger.info("Security module fully initialized")


# Exports
__all__ = [
    "init_security",
    "DEFAULT_SECURITY_CONFIG",
]
