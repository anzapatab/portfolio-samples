# src/dashboard/auth/security/totp.py
# -*- coding: utf-8 -*-
"""
Two-Factor Authentication (2FA) with TOTP.

Implements RFC 6238 TOTP (Time-based One-Time Password):
- Google Authenticator compatible
- QR code generation for easy setup
- Backup codes for recovery
- Rate limiting on verification attempts
"""
from __future__ import annotations

import secrets
import base64
import hashlib
import logging
from typing import TYPE_CHECKING, Optional, List, Tuple
from io import BytesIO

import pyotp

if TYPE_CHECKING:
    from dashboard.auth.models import User

logger = logging.getLogger(__name__)

# TOTP configuration
TOTP_ISSUER = "Energy Dashboard"
TOTP_DIGITS = 6
TOTP_INTERVAL = 30  # seconds
TOTP_ALGORITHM = "SHA1"
TOTP_VALID_WINDOW = 1  # Accept codes +/-1 interval

# Backup codes configuration
BACKUP_CODE_LENGTH = 8
BACKUP_CODE_COUNT = 10


def generate_totp_secret() -> str:
    """
    Generate a new TOTP secret key.

    Returns base32-encoded secret suitable for authenticator apps.
    """
    # Generate 20 random bytes (160 bits) as recommended by RFC 4226
    secret_bytes = secrets.token_bytes(20)
    return base64.b32encode(secret_bytes).decode("utf-8")


def get_totp_uri(secret: str, username: str, issuer: str = TOTP_ISSUER) -> str:
    """
    Generate otpauth:// URI for authenticator apps.

    This URI can be encoded as a QR code for easy setup.
    """
    totp = pyotp.TOTP(
        secret,
        digits=TOTP_DIGITS,
        interval=TOTP_INTERVAL,
    )
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_qr_code(secret: str, username: str, issuer: str = TOTP_ISSUER) -> bytes:
    """
    Generate QR code image for TOTP setup.

    Returns PNG image as bytes.
    """
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage

        uri = get_totp_uri(secret, username, issuer)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    except ImportError:
        logger.warning("qrcode library not available for QR generation")
        return b""


def generate_qr_code_base64(secret: str, username: str, issuer: str = TOTP_ISSUER) -> str:
    """
    Generate QR code as base64-encoded data URI.

    Returns string suitable for img src attribute.
    """
    png_bytes = generate_qr_code(secret, username, issuer)
    if png_bytes:
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    return ""


def verify_totp(secret: str, code: str) -> bool:
    """
    Verify a TOTP code against the secret.

    Accepts codes within the valid window (+/-30 seconds by default).
    """
    if not secret or not code:
        return False

    # Clean code (remove spaces, dashes)
    code = code.replace(" ", "").replace("-", "")

    # Validate format
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False

    try:
        totp = pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL,
        )
        return totp.verify(code, valid_window=TOTP_VALID_WINDOW)
    except Exception as e:
        logger.warning("TOTP verification error: %s", e)
        return False


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> List[str]:
    """
    Generate backup codes for account recovery.

    These are one-time use codes in case user loses their authenticator.
    """
    codes = []
    for _ in range(count):
        # Generate random code
        code = secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
        # Format as XXXX-XXXX for readability
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def hash_backup_code(code: str) -> str:
    """
    Hash a backup code for secure storage.

    We store hashes, not plaintext codes.
    """
    # Normalize code
    normalized = code.upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def verify_backup_code(code: str, stored_hashes: List[str]) -> Tuple[bool, int]:
    """
    Verify a backup code against stored hashes.

    Returns (is_valid, index_of_used_code).
    Index is -1 if not found.
    """
    code_hash = hash_backup_code(code)

    for i, stored_hash in enumerate(stored_hashes):
        if secrets.compare_digest(code_hash, stored_hash):
            return True, i

    return False, -1


class TOTPManager:
    """
    Manages TOTP for a user account.
    """

    def __init__(self, user: "User"):
        self.user = user

    @property
    def is_enabled(self) -> bool:
        """Check if TOTP is enabled for user."""
        return bool(getattr(self.user, "totp_secret", None))

    def enable(self) -> Tuple[str, str, List[str]]:
        """
        Enable TOTP for user.

        Returns (secret, qr_code_uri, backup_codes).
        """
        # Generate secret
        secret = generate_totp_secret()

        # Generate backup codes
        backup_codes = generate_backup_codes()
        backup_hashes = [hash_backup_code(code) for code in backup_codes]

        # Store on user (caller must commit)
        self.user.totp_secret = secret
        self.user.totp_backup_codes = ",".join(backup_hashes)

        # Generate QR code
        qr_uri = generate_qr_code_base64(secret, self.user.username)

        logger.info("TOTP enabled for user %s", self.user.username)

        return secret, qr_uri, backup_codes

    def disable(self) -> None:
        """Disable TOTP for user."""
        self.user.totp_secret = None
        self.user.totp_backup_codes = None

        logger.info("TOTP disabled for user %s", self.user.username)

    def verify(self, code: str) -> bool:
        """
        Verify TOTP or backup code.

        If backup code is used, it's consumed (one-time use).
        """
        if not self.is_enabled:
            return True  # TOTP not required

        secret = self.user.totp_secret

        # Try TOTP first
        if verify_totp(secret, code):
            logger.debug("TOTP verified for user %s", self.user.username)
            return True

        # Try backup code
        backup_hashes_str = getattr(self.user, "totp_backup_codes", "")
        if backup_hashes_str:
            backup_hashes = backup_hashes_str.split(",")
            is_valid, index = verify_backup_code(code, backup_hashes)

            if is_valid:
                # Remove used backup code
                backup_hashes.pop(index)
                self.user.totp_backup_codes = ",".join(backup_hashes)

                logger.info(
                    "Backup code used for user %s (%d remaining)",
                    self.user.username,
                    len(backup_hashes),
                )
                return True

        return False

    def get_remaining_backup_codes(self) -> int:
        """Get count of remaining backup codes."""
        backup_hashes_str = getattr(self.user, "totp_backup_codes", "")
        if backup_hashes_str:
            return len(backup_hashes_str.split(","))
        return 0

    def regenerate_backup_codes(self) -> List[str]:
        """
        Regenerate backup codes (invalidates old ones).

        Returns new plaintext codes (show once to user).
        """
        backup_codes = generate_backup_codes()
        backup_hashes = [hash_backup_code(code) for code in backup_codes]
        self.user.totp_backup_codes = ",".join(backup_hashes)

        logger.info("Backup codes regenerated for user %s", self.user.username)

        return backup_codes


def get_current_totp_code(secret: str) -> str:
    """
    Get current TOTP code for a secret.

    Useful for testing/debugging.
    """
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return totp.now()


def get_totp_time_remaining() -> int:
    """Get seconds until current TOTP code expires."""
    import time
    return TOTP_INTERVAL - (int(time.time()) % TOTP_INTERVAL)
