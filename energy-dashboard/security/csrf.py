# src/dashboard/auth/security/csrf.py
# -*- coding: utf-8 -*-
"""
CSRF (Cross-Site Request Forgery) protection.

Implements:
- Token-based CSRF protection
- Double submit cookie pattern
- Origin/Referer validation
- SameSite cookie enforcement
"""
from __future__ import annotations

import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# CSRF configuration
CSRF_TOKEN_LENGTH = 32
CSRF_TOKEN_EXPIRY_HOURS = 24
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "__app_csrf"
CSRF_FORM_FIELD = "csrf_token"

# Secret key for HMAC (set during init)
_csrf_secret: Optional[str] = None


def generate_csrf_token(user_id: int = None) -> str:
    """
    Generate a CSRF token.

    The token is bound to the user session if provided.
    Uses | as separator to avoid conflicts with colons in ISO timestamps.
    """
    # Random component
    random_part = secrets.token_urlsafe(CSRF_TOKEN_LENGTH)

    # Timestamp for expiry checking
    timestamp = datetime.utcnow().isoformat()

    # Create token data using | as separator (ISO timestamps contain colons)
    data = f"{random_part}|{timestamp}"

    if user_id:
        data = f"{data}|{user_id}"

    # Sign with HMAC
    if _csrf_secret:
        signature = hmac.new(
            _csrf_secret.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        return f"{data}|{signature}"

    return data


def validate_csrf_token(token: str, user_id: int = None) -> tuple[bool, str]:
    """
    Validate a CSRF token.

    Returns (is_valid, error_message).
    Uses | as separator (to avoid conflicts with colons in ISO timestamps).
    """
    if not token:
        return False, "CSRF token missing"

    try:
        parts = token.split("|")

        if len(parts) < 2:
            return False, "Invalid CSRF token format"

        # Extract timestamp
        timestamp_str = parts[1]
        timestamp = datetime.fromisoformat(timestamp_str)

        # Check expiry
        if datetime.utcnow() - timestamp > timedelta(hours=CSRF_TOKEN_EXPIRY_HOURS):
            return False, "CSRF token expired"

        # Verify signature if present
        if _csrf_secret and len(parts) >= 3:
            provided_signature = parts[-1]
            data = "|".join(parts[:-1])

            expected_signature = hmac.new(
                _csrf_secret.encode(),
                data.encode(),
                hashlib.sha256
            ).hexdigest()[:16]

            if not hmac.compare_digest(provided_signature, expected_signature):
                return False, "Invalid CSRF token signature"

        # Verify user binding if provided
        if user_id and len(parts) >= 4:
            token_user_id = parts[2]
            if str(user_id) != token_user_id:
                return False, "CSRF token user mismatch"

        return True, ""

    except Exception as e:
        logger.warning("CSRF validation error: %s", e)
        return False, "CSRF validation failed"


def validate_origin(request) -> tuple[bool, str]:
    """
    Validate request origin headers.

    Checks Origin and Referer headers against allowed origins.
    """
    from flask import current_app

    # Get allowed origins from config
    allowed_origins = current_app.config.get("CSRF_ALLOWED_ORIGINS", [])

    # Get request host
    request_host = request.host.split(":")[0]

    # Check Origin header (preferred)
    origin = request.headers.get("Origin")
    if origin:
        origin_host = origin.split("//")[-1].split("/")[0].split(":")[0]

        if origin_host == request_host:
            return True, ""

        if origin_host in allowed_origins:
            return True, ""

        return False, f"Origin {origin} not allowed"

    # Fall back to Referer header
    referer = request.headers.get("Referer")
    if referer:
        referer_host = referer.split("//")[-1].split("/")[0].split(":")[0]

        if referer_host == request_host:
            return True, ""

        if referer_host in allowed_origins:
            return True, ""

        return False, f"Referer {referer} not allowed"

    # No Origin or Referer - could be direct request
    # Allow for GET/HEAD, block for state-changing methods
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True, ""

    return False, "Missing Origin/Referer header"


def csrf_protect(f: Callable) -> Callable:
    """
    Decorator to enforce CSRF protection on an endpoint.

    Validates CSRF token from header or form field.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        from flask import request, jsonify

        # Skip for safe methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return f(*args, **kwargs)

        # Validate origin
        origin_valid, origin_error = validate_origin(request)
        if not origin_valid:
            logger.warning("CSRF origin validation failed: %s", origin_error)
            return jsonify({"error": "CSRF validation failed"}), 403

        # Get token from header or form
        token = request.headers.get(CSRF_HEADER_NAME)
        if not token:
            token = request.form.get(CSRF_FORM_FIELD)
        if not token and request.is_json:
            token = request.json.get(CSRF_FORM_FIELD)

        # Validate token
        user_id = None
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                user_id = current_user.id
        except Exception:
            pass

        is_valid, error = validate_csrf_token(token, user_id)
        if not is_valid:
            logger.warning("CSRF token validation failed: %s", error)
            from .audit_logger import log_event, AuditEventType, AuditSeverity
            log_event(
                event_type=AuditEventType.CSRF_VIOLATION,
                severity=AuditSeverity.WARNING,
                details={"error": error},
                success=False,
            )
            return jsonify({"error": "CSRF validation failed"}), 403

        return f(*args, **kwargs)

    return wrapped


def init_csrf_protection(flask_app: Flask) -> None:
    """
    Initialize CSRF protection.
    """
    global _csrf_secret

    # Use Flask secret key for CSRF
    _csrf_secret = flask_app.config.get("SECRET_KEY", "")

    # Add CSRF token to response cookies
    @flask_app.after_request
    def set_csrf_cookie(response):
        from flask import request

        # Only set for HTML responses
        if "text/html" in response.content_type:
            user_id = None
            try:
                from flask_login import current_user
                if current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass

            token = generate_csrf_token(user_id)
            response.set_cookie(
                CSRF_COOKIE_NAME,
                token,
                httponly=False,  # JS needs to read this
                secure=True,
                samesite="Lax",
                max_age=CSRF_TOKEN_EXPIRY_HOURS * 3600,
            )

        return response

    # Add helper to get token in templates/responses
    @flask_app.context_processor
    def csrf_context():
        def get_csrf_token():
            user_id = None
            try:
                from flask_login import current_user
                if current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass
            return generate_csrf_token(user_id)

        return {"csrf_token": get_csrf_token}

    logger.info("CSRF protection initialized")


def get_csrf_token_for_api() -> dict:
    """
    Get CSRF token for API responses.

    Returns dict with token and header name.
    """
    from flask_login import current_user

    user_id = None
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
    except Exception:
        pass

    return {
        "csrf_token": generate_csrf_token(user_id),
        "csrf_header": CSRF_HEADER_NAME,
    }
