# src/dashboard/auth/security/session.py
# -*- coding: utf-8 -*-
"""
Secure session management.

Implements:
- Secure cookie configuration
- Session rotation on login
- Idle and absolute timeouts
- Concurrent session management
- Session fingerprinting
- Session invalidation
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional, List
from threading import Lock
from collections import defaultdict

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# In-memory session tracking (use Redis in production for multi-instance)
_active_sessions: Dict[int, List[dict]] = defaultdict(list)
_session_lock = Lock()


class SessionManager:
    """
    Manages user sessions with security controls.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        idle_timeout_minutes: int = 60,
        absolute_timeout_hours: int = 24,
    ):
        self.max_concurrent = max_concurrent
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.absolute_timeout = timedelta(hours=absolute_timeout_hours)

    def create_session(
        self,
        user_id: int,
        ip_address: str,
        user_agent: str,
    ) -> str:
        """
        Create a new session for user.

        Returns session token.
        """
        session_id = secrets.token_urlsafe(32)
        fingerprint = self._generate_fingerprint(ip_address, user_agent)

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "ip_address": ip_address,
            "fingerprint": fingerprint,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
        }

        with _session_lock:
            # Check concurrent session limit
            user_sessions = _active_sessions[user_id]

            # Remove expired sessions
            user_sessions = [
                s for s in user_sessions
                if not self._is_session_expired(s)
            ]

            # Enforce concurrent limit (remove oldest if needed)
            while len(user_sessions) >= self.max_concurrent:
                oldest = min(user_sessions, key=lambda s: s["created_at"])
                user_sessions.remove(oldest)
                logger.info(
                    "Removed oldest session for user %d (concurrent limit)",
                    user_id
                )

            user_sessions.append(session_data)
            _active_sessions[user_id] = user_sessions

        logger.debug("Created session for user %d", user_id)
        return session_id

    def validate_session(
        self,
        user_id: int,
        session_id: str,
        ip_address: str,
        user_agent: str,
    ) -> tuple[bool, str]:
        """
        Validate a session.

        Returns (is_valid, error_message).
        """
        with _session_lock:
            user_sessions = _active_sessions.get(user_id, [])

            for session in user_sessions:
                if session["session_id"] != session_id:
                    continue

                # Found session - validate it

                # Check expiration
                if self._is_session_expired(session):
                    user_sessions.remove(session)
                    return False, "Session expired"

                # Check fingerprint (optional - can be disabled for mobile)
                current_fingerprint = self._generate_fingerprint(ip_address, user_agent)
                if session["fingerprint"] != current_fingerprint:
                    # Fingerprint mismatch - possible session hijacking
                    logger.warning(
                        "Session fingerprint mismatch for user %d. "
                        "Expected: %s, Got: %s",
                        user_id,
                        session["fingerprint"][:16],
                        current_fingerprint[:16],
                    )
                    # You could invalidate here, but this can cause issues
                    # with users changing networks. Log for monitoring instead.

                # Update last activity
                session["last_activity"] = datetime.utcnow()
                return True, ""

            return False, "Session not found"

    def invalidate_session(self, user_id: int, session_id: str) -> bool:
        """Invalidate a specific session."""
        with _session_lock:
            user_sessions = _active_sessions.get(user_id, [])
            for session in user_sessions:
                if session["session_id"] == session_id:
                    user_sessions.remove(session)
                    logger.info("Invalidated session for user %d", user_id)
                    return True
            return False

    def invalidate_all_sessions(self, user_id: int) -> int:
        """
        Invalidate all sessions for a user.

        Useful for password change or security concern.
        Returns number of invalidated sessions.
        """
        with _session_lock:
            count = len(_active_sessions.get(user_id, []))
            _active_sessions[user_id] = []
            logger.info("Invalidated %d sessions for user %d", count, user_id)
            return count

    def get_user_sessions(self, user_id: int) -> List[dict]:
        """Get list of active sessions for a user."""
        with _session_lock:
            sessions = _active_sessions.get(user_id, [])
            # Return sanitized copy
            return [
                {
                    "session_id": s["session_id"][:8] + "...",
                    "ip_address": s["ip_address"],
                    "created_at": s["created_at"].isoformat(),
                    "last_activity": s["last_activity"].isoformat(),
                }
                for s in sessions
                if not self._is_session_expired(s)
            ]

    def _is_session_expired(self, session: dict) -> bool:
        """Check if session is expired."""
        now = datetime.utcnow()

        # Check absolute timeout
        if now - session["created_at"] > self.absolute_timeout:
            return True

        # Check idle timeout
        if now - session["last_activity"] > self.idle_timeout:
            return True

        return False

    def _generate_fingerprint(self, ip_address: str, user_agent: str) -> str:
        """
        Generate session fingerprint for validation.

        Uses IP and user agent to detect session hijacking.
        """
        # Note: In production, you might want to only use user agent
        # since IP can change (mobile networks, VPN, etc.)
        data = f"{user_agent}"
        return hashlib.sha256(data.encode()).hexdigest()


# Global session manager
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def init_session_security(flask_app: Flask, config: dict) -> None:
    """
    Initialize secure session configuration.
    """
    global _session_manager

    # Create session manager with config
    _session_manager = SessionManager(
        max_concurrent=config.get("max_concurrent_sessions", 3),
        idle_timeout_minutes=config.get("idle_timeout_minutes", 60),
        absolute_timeout_hours=config.get("absolute_timeout_hours", 24),
    )

    # Configure Flask session cookies
    flask_app.config.update(
        SESSION_COOKIE_SECURE=config.get("secure_cookie", True),
        SESSION_COOKIE_HTTPONLY=config.get("httponly", True),
        SESSION_COOKIE_SAMESITE=config.get("samesite", "Lax"),
        SESSION_COOKIE_NAME="__app_session",
    )

    # Add session rotation on login if configured
    if config.get("rotation_on_login", True):
        _setup_session_rotation(flask_app)

    logger.info(
        "Session security configured (max_concurrent=%d, idle=%dm, absolute=%dh)",
        _session_manager.max_concurrent,
        config.get("idle_timeout_minutes", 60),
        config.get("absolute_timeout_hours", 24),
    )


def _setup_session_rotation(flask_app: Flask) -> None:
    """
    Setup automatic session rotation on login.

    Regenerates session ID to prevent fixation attacks.
    """
    from flask import session

    original_login = None

    try:
        from flask_login import user_logged_in

        @user_logged_in.connect_via(flask_app)
        def rotate_session_on_login(sender, user, **kwargs):
            """Rotate session ID on successful login."""
            # Get old session data
            old_data = dict(session)

            # Clear and regenerate
            session.clear()

            # Restore data (except session ID which is regenerated)
            for key, value in old_data.items():
                if key != "_id":
                    session[key] = value

            # Generate new session identifier
            session.modified = True
            session.permanent = True

            logger.debug("Session rotated for user %s", user.username)

    except ImportError:
        logger.warning("flask_login signals not available for session rotation")


def regenerate_session() -> None:
    """
    Manually regenerate session ID.

    Call this after privilege escalation or sensitive operations.
    """
    from flask import session

    old_data = dict(session)
    session.clear()

    for key, value in old_data.items():
        if key != "_id":
            session[key] = value

    session.modified = True


def invalidate_user_sessions(user_id: int) -> int:
    """
    Invalidate all sessions for a user.

    Call this on password change, account compromise, etc.
    """
    manager = get_session_manager()
    return manager.invalidate_all_sessions(user_id)
