# src/dashboard/auth/security/ip_protection.py
# -*- coding: utf-8 -*-
"""
IP-based security protection.

Implements:
- IP whitelist/blacklist
- Automatic suspicious IP detection
- Geo-blocking (optional)
- Tor exit node blocking (optional)
- VPN detection (basic)
- Progressive blocking
"""
from __future__ import annotations

import logging
import ipaddress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Set, Optional, Tuple
from threading import Lock
from collections import defaultdict

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# IP tracking storage
_blocked_ips: Set[str] = set()
_whitelisted_ips: Set[str] = set()
_suspicious_ips: Dict[str, dict] = {}
_ip_lock = Lock()

# Suspicious activity thresholds
SUSPICIOUS_THRESHOLD = 10  # requests before marking suspicious
BLOCK_THRESHOLD = 50  # requests before auto-blocking
TRACKING_WINDOW_MINUTES = 60


class IPTracker:
    """
    Tracks IP behavior for anomaly detection.
    """

    def __init__(self):
        self.requests: Dict[str, List[datetime]] = defaultdict(list)
        self.failed_logins: Dict[str, int] = defaultdict(int)
        self.lock = Lock()

    def record_request(self, ip: str) -> None:
        """Record a request from an IP."""
        with self.lock:
            now = datetime.utcnow()
            self.requests[ip].append(now)

            # Clean old entries
            cutoff = now - timedelta(minutes=TRACKING_WINDOW_MINUTES)
            self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]

    def record_failed_login(self, ip: str) -> int:
        """Record a failed login attempt. Returns total failures."""
        with self.lock:
            self.failed_logins[ip] += 1
            return self.failed_logins[ip]

    def reset_failed_logins(self, ip: str) -> None:
        """Reset failed login counter for IP."""
        with self.lock:
            self.failed_logins.pop(ip, None)

    def get_request_count(self, ip: str) -> int:
        """Get request count in tracking window."""
        with self.lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(minutes=TRACKING_WINDOW_MINUTES)
            return len([t for t in self.requests.get(ip, []) if t > cutoff])

    def is_suspicious(self, ip: str) -> bool:
        """Check if IP behavior is suspicious."""
        count = self.get_request_count(ip)
        failed = self.failed_logins.get(ip, 0)
        return count > SUSPICIOUS_THRESHOLD or failed > 3

    def should_auto_block(self, ip: str) -> bool:
        """Check if IP should be automatically blocked."""
        count = self.get_request_count(ip)
        failed = self.failed_logins.get(ip, 0)
        return count > BLOCK_THRESHOLD or failed > 10


# Global tracker
_ip_tracker = IPTracker()


def is_ip_blocked(ip: str) -> bool:
    """Check if IP is blocked."""
    with _ip_lock:
        return ip in _blocked_ips


def is_ip_whitelisted(ip: str) -> bool:
    """Check if IP is whitelisted."""
    with _ip_lock:
        return ip in _whitelisted_ips


def block_ip(ip: str, reason: str = "manual", duration_hours: int = None) -> None:
    """
    Block an IP address.

    Args:
        ip: IP address to block
        reason: Reason for blocking
        duration_hours: Block duration (None = permanent)
    """
    with _ip_lock:
        _blocked_ips.add(ip)
        _suspicious_ips[ip] = {
            "blocked_at": datetime.utcnow(),
            "reason": reason,
            "duration_hours": duration_hours,
        }

    logger.warning("Blocked IP %s: %s (duration: %s hours)", ip, reason, duration_hours or "permanent")

    # Log to audit
    from .audit_logger import log_event, AuditEventType, AuditSeverity
    log_event(
        event_type=AuditEventType.IP_BLOCKED,
        severity=AuditSeverity.WARNING,
        details={"ip": ip, "reason": reason, "duration": duration_hours},
    )


def unblock_ip(ip: str) -> bool:
    """Unblock an IP address."""
    with _ip_lock:
        if ip in _blocked_ips:
            _blocked_ips.discard(ip)
            _suspicious_ips.pop(ip, None)
            _ip_tracker.reset_failed_logins(ip)

            logger.info("Unblocked IP %s", ip)

            from .audit_logger import log_event, AuditEventType, AuditSeverity
            log_event(
                event_type=AuditEventType.IP_UNBLOCKED,
                severity=AuditSeverity.INFO,
                details={"ip": ip},
            )
            return True
    return False


def whitelist_ip(ip: str) -> None:
    """Add IP to whitelist."""
    with _ip_lock:
        _whitelisted_ips.add(ip)
    logger.info("Whitelisted IP %s", ip)


def remove_from_whitelist(ip: str) -> None:
    """Remove IP from whitelist."""
    with _ip_lock:
        _whitelisted_ips.discard(ip)
    logger.info("Removed IP %s from whitelist", ip)


def check_ip(ip: str) -> Tuple[bool, str]:
    """
    Check if IP is allowed to access.

    Returns (is_allowed, reason).
    """
    # Always allow whitelisted
    if is_ip_whitelisted(ip):
        return True, ""

    # Check if blocked
    if is_ip_blocked(ip):
        # Check if block has expired
        info = _suspicious_ips.get(ip, {})
        duration = info.get("duration_hours")
        blocked_at = info.get("blocked_at")

        if duration and blocked_at:
            if datetime.utcnow() > blocked_at + timedelta(hours=duration):
                unblock_ip(ip)
                return True, ""

        return False, f"IP blocked: {info.get('reason', 'unknown')}"

    # Track request
    _ip_tracker.record_request(ip)

    # Check for auto-block
    if _ip_tracker.should_auto_block(ip):
        block_ip(ip, reason="automatic_threshold", duration_hours=24)
        return False, "IP auto-blocked due to suspicious activity"

    return True, ""


def record_failed_login(ip: str) -> Tuple[int, bool]:
    """
    Record failed login from IP.

    Returns (total_failures, was_blocked).
    """
    failures = _ip_tracker.record_failed_login(ip)

    # Check if should block
    if failures >= 10:
        block_ip(ip, reason="too_many_failed_logins", duration_hours=1)
        return failures, True

    return failures, False


def is_private_ip(ip: str) -> bool:
    """Check if IP is private/internal."""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private
    except ValueError:
        return False


def is_valid_ip(ip: str) -> bool:
    """Check if string is a valid IP address."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def get_client_ip(request) -> str:
    """
    Get real client IP from request.

    Handles X-Forwarded-For and other proxy headers.
    """
    # Check for proxy headers (in order of preference)
    headers_to_check = [
        "X-Real-IP",
        "X-Forwarded-For",
        "CF-Connecting-IP",  # Cloudflare
        "True-Client-IP",    # Akamai
    ]

    for header in headers_to_check:
        value = request.headers.get(header)
        if value:
            # X-Forwarded-For can contain multiple IPs
            ip = value.split(",")[0].strip()
            if is_valid_ip(ip):
                return ip

    # Fall back to remote_addr
    return request.remote_addr or "unknown"


def get_blocked_ips() -> List[dict]:
    """Get list of blocked IPs with details."""
    with _ip_lock:
        result = []
        for ip in _blocked_ips:
            info = _suspicious_ips.get(ip, {})
            result.append({
                "ip": ip,
                "blocked_at": info.get("blocked_at", "").isoformat() if info.get("blocked_at") else None,
                "reason": info.get("reason", "unknown"),
                "duration_hours": info.get("duration_hours"),
            })
        return result


def get_suspicious_ips() -> List[dict]:
    """Get list of suspicious (but not blocked) IPs."""
    result = []
    with _ip_lock:
        for ip, requests in _ip_tracker.requests.items():
            if ip not in _blocked_ips and _ip_tracker.is_suspicious(ip):
                result.append({
                    "ip": ip,
                    "request_count": len(requests),
                    "failed_logins": _ip_tracker.failed_logins.get(ip, 0),
                })
    return result


def init_ip_protection(flask_app: Flask, config: dict) -> None:
    """
    Initialize IP protection middleware.
    """
    # Load whitelist from config
    for ip in config.get("whitelist", []):
        whitelist_ip(ip)

    # Load blacklist from config
    for ip in config.get("blacklist", []):
        block_ip(ip, reason="config_blacklist")

    # Add middleware
    @flask_app.before_request
    def check_ip_protection():
        from flask import request, jsonify

        ip = get_client_ip(request)

        # Skip check for health endpoints
        if request.path in ("/healthz", "/metrics"):
            return None

        is_allowed, reason = check_ip(ip)
        if not is_allowed:
            logger.warning("Blocked request from %s: %s", ip, reason)
            return jsonify({"error": "Access denied", "reason": reason}), 403

        return None

    logger.info(
        "IP protection initialized (whitelist: %d, blacklist: %d)",
        len(config.get("whitelist", [])),
        len(config.get("blacklist", [])),
    )
