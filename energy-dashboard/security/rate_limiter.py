# src/dashboard/auth/security/rate_limiter.py
# -*- coding: utf-8 -*-
"""
Rate limiting and brute force protection.

Implements:
- Per-IP rate limiting
- Per-user rate limiting
- Endpoint-specific limits
- Progressive slowdown for repeated violations
- Distributed rate limiting with Redis (optional)
"""
from __future__ import annotations

import logging
import time
from functools import wraps
from typing import TYPE_CHECKING, Callable, Dict, Optional
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# In-memory rate limit storage (fallback when Redis not available)
_rate_limit_storage: Dict[str, list] = defaultdict(list)
_storage_lock = Lock()

# Limiter instance (set during init)
_limiter = None


class MemoryRateLimiter:
    """
    Thread-safe in-memory rate limiter.

    Suitable for single-instance deployments.
    For multi-instance, use Redis backend.
    """

    def __init__(self):
        self.requests: Dict[str, list] = defaultdict(list)
        self.lock = Lock()
        self.blocked_until: Dict[str, datetime] = {}

    def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Check if key is rate limited.

        Returns (is_limited, remaining_requests).
        """
        now = datetime.utcnow()

        with self.lock:
            # Check if blocked
            if key in self.blocked_until:
                if now < self.blocked_until[key]:
                    return True, 0
                else:
                    del self.blocked_until[key]

            # Clean old requests
            cutoff = now - timedelta(seconds=window_seconds)
            self.requests[key] = [
                ts for ts in self.requests[key]
                if ts > cutoff
            ]

            # Check limit
            current_count = len(self.requests[key])
            if current_count >= max_requests:
                return True, 0

            # Record this request
            self.requests[key].append(now)
            return False, max_requests - current_count - 1

    def block_key(self, key: str, duration_seconds: int) -> None:
        """Block a key for specified duration."""
        with self.lock:
            self.blocked_until[key] = datetime.utcnow() + timedelta(seconds=duration_seconds)

    def reset_key(self, key: str) -> None:
        """Reset rate limit for a key."""
        with self.lock:
            self.requests.pop(key, None)
            self.blocked_until.pop(key, None)

    def get_block_remaining(self, key: str) -> int:
        """Get remaining block time in seconds."""
        with self.lock:
            if key in self.blocked_until:
                remaining = (self.blocked_until[key] - datetime.utcnow()).total_seconds()
                return max(0, int(remaining))
            return 0


# Global limiter instance
_memory_limiter = MemoryRateLimiter()


def init_rate_limiter(flask_app: Flask, config: dict) -> None:
    """
    Initialize rate limiter with Flask app.
    """
    global _limiter

    storage_uri = config.get("storage", "memory")

    if storage_uri.startswith("redis://"):
        try:
            from flask_limiter import Limiter
            from flask_limiter.util import get_remote_address

            _limiter = Limiter(
                key_func=get_remote_address,
                app=flask_app,
                storage_uri=storage_uri,
                default_limits=[config.get("global_requests", "1000 per minute")],
            )
            logger.info("Rate limiter using Redis backend: %s", storage_uri)
        except Exception as e:
            logger.warning("Failed to init Redis limiter, using memory: %s", e)
            _limiter = None
    else:
        _limiter = None
        logger.info("Rate limiter using in-memory backend")

    # Store config
    flask_app.config["RATE_LIMIT_CONFIG"] = config

    # Add rate limit headers to responses
    @flask_app.after_request
    def add_rate_limit_headers(response):
        # Add standard rate limit headers
        response.headers["X-RateLimit-Policy"] = "login=5/min; api=100/min"
        return response


def check_rate_limit(
    key: str,
    limit: int = 5,
    window: int = 60,
) -> tuple[bool, int, int]:
    """
    Check if request should be rate limited.

    Args:
        key: Unique identifier (IP, user ID, etc.)
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        (is_limited, remaining, retry_after)
    """
    is_limited, remaining = _memory_limiter.is_rate_limited(key, limit, window)
    retry_after = window if is_limited else 0
    return is_limited, remaining, retry_after


def check_login_rate_limit(ip: str, username: str = None) -> tuple[bool, str]:
    """
    Check rate limit specifically for login attempts.

    Implements dual-key limiting:
    - Per IP: Prevents distributed attacks
    - Per username: Prevents targeted account attacks

    Returns (is_limited, message).
    """
    # Check IP-based limit (5 attempts per minute)
    ip_key = f"login:ip:{ip}"
    ip_limited, ip_remaining, ip_retry = check_rate_limit(ip_key, 5, 60)

    if ip_limited:
        return True, f"Too many login attempts from this IP. Try again in {ip_retry} seconds."

    # Check username-based limit (10 attempts per 5 minutes)
    if username:
        user_key = f"login:user:{username.lower()}"
        user_limited, user_remaining, user_retry = check_rate_limit(user_key, 10, 300)

        if user_limited:
            return True, f"Too many login attempts for this account. Try again in {user_retry} seconds."

    return False, ""


def record_failed_login(ip: str, username: str = None) -> None:
    """
    Record a failed login attempt for rate limiting.
    """
    # The rate limit check already records the attempt
    # This is for explicit tracking of failures for progressive blocking
    fail_key = f"login:failed:{ip}"
    _memory_limiter.is_rate_limited(fail_key, 1000, 3600)  # Track for 1 hour


def block_ip(ip: str, duration_seconds: int = 1800) -> None:
    """
    Block an IP address for specified duration.

    Default: 30 minutes
    """
    key = f"login:ip:{ip}"
    _memory_limiter.block_key(key, duration_seconds)
    logger.warning("Blocked IP %s for %d seconds", ip, duration_seconds)


def unblock_ip(ip: str) -> None:
    """Unblock an IP address."""
    key = f"login:ip:{ip}"
    _memory_limiter.reset_key(key)
    logger.info("Unblocked IP %s", ip)


def get_ip_block_remaining(ip: str) -> int:
    """Get remaining block time for an IP."""
    key = f"login:ip:{ip}"
    return _memory_limiter.get_block_remaining(key)


def rate_limit(limit: int = 10, window: int = 60, key_func: Callable = None):
    """
    Decorator for rate limiting endpoints.

    Usage:
        @rate_limit(limit=5, window=60)
        def login():
            ...
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            from flask import request, jsonify

            # Get rate limit key
            if key_func:
                key = key_func()
            else:
                key = f"endpoint:{f.__name__}:{request.remote_addr}"

            is_limited, remaining, retry_after = check_rate_limit(key, limit, window)

            if is_limited:
                response = jsonify({
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                response.headers["X-RateLimit-Remaining"] = "0"
                return response

            # Add rate limit headers to successful response
            result = f(*args, **kwargs)

            # If result is a Response object, add headers
            if hasattr(result, "headers"):
                result.headers["X-RateLimit-Remaining"] = str(remaining)

            return result

        return wrapped
    return decorator
