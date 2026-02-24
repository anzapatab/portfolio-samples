# src/dashboard/auth/security/audit_logger.py
# -*- coding: utf-8 -*-
"""
Security audit logging system.

Provides comprehensive logging of security-relevant events:
- Authentication attempts (success/failure)
- Authorization decisions
- Password changes
- Account modifications
- Suspicious activity
- Admin actions

Logs are structured for SIEM integration and compliance.
"""
from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, Any
from enum import Enum
from functools import wraps

if TYPE_CHECKING:
    from flask import Flask

# Dedicated security audit logger
audit_logger = logging.getLogger("security.audit")


class AuditEventType(str, Enum):
    """Security event types for audit logging."""

    # Authentication events
    LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
    LOGIN_BLOCKED = "AUTH_LOGIN_BLOCKED"
    LOGOUT = "AUTH_LOGOUT"
    SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    SESSION_INVALIDATED = "AUTH_SESSION_INVALIDATED"

    # Account events
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    ACCOUNT_MODIFIED = "ACCOUNT_MODIFIED"
    ACCOUNT_DELETED = "ACCOUNT_DELETED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"
    ACCOUNT_ACTIVATED = "ACCOUNT_ACTIVATED"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"

    # Password events
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    PASSWORD_POLICY_VIOLATION = "PASSWORD_POLICY_VIOLATION"

    # 2FA events
    TOTP_ENABLED = "TOTP_ENABLED"
    TOTP_DISABLED = "TOTP_DISABLED"
    TOTP_VERIFIED = "TOTP_VERIFIED"
    TOTP_FAILED = "TOTP_FAILED"

    # Authorization events
    ACCESS_GRANTED = "ACCESS_GRANTED"
    ACCESS_DENIED = "ACCESS_DENIED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    ROLE_CHANGED = "ROLE_CHANGED"

    # Security events
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    IP_BLOCKED = "IP_BLOCKED"
    IP_UNBLOCKED = "IP_UNBLOCKED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    BRUTE_FORCE_DETECTED = "BRUTE_FORCE_DETECTED"
    CSRF_VIOLATION = "CSRF_VIOLATION"

    # Admin events
    ADMIN_ACTION = "ADMIN_ACTION"
    CONFIG_CHANGED = "CONFIG_CHANGED"
    USER_IMPERSONATION = "USER_IMPERSONATION"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditLog:
    """
    Structured audit log entry.
    """

    def __init__(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ):
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.event_type = event_type
        self.severity = severity
        self.user_id = user_id
        self.username = username
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.resource = resource
        self.action = action
        self.details = details or {}
        self.success = success

        # Generate unique event ID
        self.event_id = self._generate_event_id()

    def _generate_event_id(self) -> str:
        """Generate unique event ID for correlation."""
        data = f"{self.timestamp}:{self.event_type}:{self.ip_address}:{self.user_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "username": self.username,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "resource": self.resource,
            "action": self.action,
            "success": self.success,
            "details": self.details,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


def _get_request_context() -> Dict[str, Any]:
    """Extract request context for audit logging."""
    try:
        from flask import request, has_request_context

        if not has_request_context():
            return {}

        return {
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", "")[:500],
            "method": request.method,
            "path": request.path,
            "referrer": request.referrer,
        }
    except Exception:
        return {}


def _get_current_user() -> Dict[str, Any]:
    """Get current user info for audit logging."""
    try:
        from flask_login import current_user

        if current_user and current_user.is_authenticated:
            return {
                "user_id": current_user.id,
                "username": current_user.username,
            }
    except Exception:
        pass

    return {"user_id": None, "username": None}


def log_event(
    event_type: AuditEventType,
    severity: AuditSeverity = AuditSeverity.INFO,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    resource: Optional[str] = None,
    action: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
) -> AuditLog:
    """
    Log a security audit event.

    Automatically captures request context and current user.
    """
    # Get request context
    ctx = _get_request_context()

    # Get current user if not provided
    if user_id is None:
        user_info = _get_current_user()
        user_id = user_info.get("user_id")
        if username is None:
            username = user_info.get("username")

    # Create audit log entry
    log_entry = AuditLog(
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        username=username,
        ip_address=ctx.get("ip_address"),
        user_agent=ctx.get("user_agent"),
        resource=resource or ctx.get("path"),
        action=action or ctx.get("method"),
        details=details,
        success=success,
    )

    # Log to security audit logger
    log_method = getattr(audit_logger, severity.value.lower(), audit_logger.info)
    log_method(log_entry.to_json())

    return log_entry


def log_login_success(user_id: int, username: str, method: str = "password") -> AuditLog:
    """Log successful login."""
    return log_event(
        event_type=AuditEventType.LOGIN_SUCCESS,
        severity=AuditSeverity.INFO,
        user_id=user_id,
        username=username,
        action="login",
        details={"method": method},
        success=True,
    )


def log_login_failure(
    username: str,
    reason: str = "invalid_credentials",
    ip_address: str = None,
) -> AuditLog:
    """Log failed login attempt."""
    details = {"reason": reason}
    if ip_address:
        details["ip_address"] = ip_address

    return log_event(
        event_type=AuditEventType.LOGIN_FAILURE,
        severity=AuditSeverity.WARNING,
        username=username,
        action="login",
        details=details,
        success=False,
    )


def log_login_blocked(
    username: str = None,
    ip_address: str = None,
    reason: str = "rate_limit",
) -> AuditLog:
    """Log blocked login attempt."""
    return log_event(
        event_type=AuditEventType.LOGIN_BLOCKED,
        severity=AuditSeverity.WARNING,
        username=username,
        action="login",
        details={"reason": reason, "blocked_ip": ip_address},
        success=False,
    )


def log_logout(user_id: int, username: str) -> AuditLog:
    """Log user logout."""
    return log_event(
        event_type=AuditEventType.LOGOUT,
        severity=AuditSeverity.INFO,
        user_id=user_id,
        username=username,
        action="logout",
        success=True,
    )


def log_password_change(
    user_id: int,
    username: str,
    changed_by: str = None,
) -> AuditLog:
    """Log password change."""
    details = {}
    if changed_by and changed_by != username:
        details["changed_by"] = changed_by
        details["admin_action"] = True

    return log_event(
        event_type=AuditEventType.PASSWORD_CHANGED,
        severity=AuditSeverity.INFO,
        user_id=user_id,
        username=username,
        action="password_change",
        details=details,
        success=True,
    )


def log_account_locked(
    user_id: int,
    username: str,
    reason: str = "failed_attempts",
    duration_minutes: int = None,
) -> AuditLog:
    """Log account lockout."""
    return log_event(
        event_type=AuditEventType.ACCOUNT_LOCKED,
        severity=AuditSeverity.WARNING,
        user_id=user_id,
        username=username,
        action="account_lock",
        details={"reason": reason, "duration_minutes": duration_minutes},
        success=True,
    )


def log_suspicious_activity(
    description: str,
    user_id: int = None,
    username: str = None,
    ip_address: str = None,
    details: Dict[str, Any] = None,
) -> AuditLog:
    """Log suspicious activity."""
    event_details = {"description": description}
    if details:
        event_details.update(details)
    if ip_address:
        event_details["suspicious_ip"] = ip_address

    return log_event(
        event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
        severity=AuditSeverity.WARNING,
        user_id=user_id,
        username=username,
        action="suspicious_activity",
        details=event_details,
        success=False,
    )


def log_brute_force_detected(
    ip_address: str,
    target_username: str = None,
    attempt_count: int = None,
) -> AuditLog:
    """Log detected brute force attack."""
    return log_event(
        event_type=AuditEventType.BRUTE_FORCE_DETECTED,
        severity=AuditSeverity.CRITICAL,
        username=target_username,
        action="brute_force_detection",
        details={
            "attacker_ip": ip_address,
            "attempt_count": attempt_count,
        },
        success=False,
    )


def log_admin_action(
    admin_user_id: int,
    admin_username: str,
    action: str,
    target_user_id: int = None,
    target_username: str = None,
    details: Dict[str, Any] = None,
) -> AuditLog:
    """Log administrative action."""
    event_details = {
        "admin_user_id": admin_user_id,
        "admin_username": admin_username,
    }
    if target_user_id:
        event_details["target_user_id"] = target_user_id
    if target_username:
        event_details["target_username"] = target_username
    if details:
        event_details.update(details)

    return log_event(
        event_type=AuditEventType.ADMIN_ACTION,
        severity=AuditSeverity.INFO,
        user_id=admin_user_id,
        username=admin_username,
        action=action,
        details=event_details,
        success=True,
    )


def audit_endpoint(event_type: AuditEventType = None):
    """
    Decorator to automatically audit endpoint access.

    Usage:
        @audit_endpoint(AuditEventType.ACCESS_GRANTED)
        def protected_resource():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                result = f(*args, **kwargs)

                # Log success
                if event_type:
                    log_event(
                        event_type=event_type,
                        severity=AuditSeverity.INFO,
                        resource=f.__name__,
                        success=True,
                    )

                return result

            except Exception as e:
                # Log failure
                log_event(
                    event_type=event_type or AuditEventType.ACCESS_DENIED,
                    severity=AuditSeverity.ERROR,
                    resource=f.__name__,
                    details={"error": str(e)},
                    success=False,
                )
                raise

        return wrapped
    return decorator


def init_audit_logger(flask_app: Flask, config: dict) -> None:
    """
    Initialize audit logging.

    Configures dedicated audit logger with structured output.
    """
    # Configure audit logger
    audit_logger.setLevel(logging.INFO)

    # Create handler if not already configured
    if not audit_logger.handlers:
        # Console handler with JSON format
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)

        # JSON formatter for SIEM integration
        formatter = logging.Formatter(
            '%(asctime)s | SECURITY_AUDIT | %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
        handler.setFormatter(formatter)

        audit_logger.addHandler(handler)

    # Store config
    flask_app.config["AUDIT_CONFIG"] = config

    # Log initialization
    log_event(
        event_type=AuditEventType.CONFIG_CHANGED,
        severity=AuditSeverity.INFO,
        action="audit_init",
        details={"config": config},
        success=True,
    )
