"""Security helpers: login-attempt throttling (F1) and TOTP 2FA (F2).

All standard-library — no extra dependencies. The throttle is in-memory (per
process); it resets on restart, which is fine for a single-container Pi deploy.
TOTP follows RFC 6238 (30s step, 6 digits, SHA1) so it interoperates with any
authenticator app (Google Authenticator, Authy, 1Password, …).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from urllib.parse import quote


# --------------------------------------------------------------------------
# F1 — login lockout: throttle repeated failed logins per key (username/IP)
# --------------------------------------------------------------------------
class LoginThrottle:
    """In-memory failed-login throttle.

    After `max_attempts` failures a key is locked for `lockout_seconds`. A
    successful login (or a lapsed lockout) clears the counter. Thread-safe.
    """

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 900) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._lock = threading.Lock()
        # key -> {"fails": int, "until": float|None}
        self._state: dict[str, dict] = {}

    def _now(self) -> float:
        return time.monotonic()

    def retry_after(self, key: str) -> int:
        """Seconds remaining on a lockout for `key`, or 0 if not locked."""
        with self._lock:
            rec = self._state.get(key)
            if not rec or not rec.get("until"):
                return 0
            remaining = rec["until"] - self._now()
            if remaining <= 0:
                # lockout lapsed — clear it so the next attempt starts fresh
                self._state.pop(key, None)
                return 0
            return int(remaining) + 1

    def record_failure(self, key: str) -> int:
        """Count a failed attempt; lock the key once the limit is hit.

        Returns the seconds the key is now locked for (0 if not yet locked).
        """
        with self._lock:
            rec = self._state.setdefault(key, {"fails": 0, "until": None})
            rec["fails"] += 1
            if rec["fails"] >= self.max_attempts:
                rec["until"] = self._now() + self.lockout_seconds
                return self.lockout_seconds
            return 0

    def reset(self, key: str) -> None:
        """Clear all failures for a key (call on successful login)."""
        with self._lock:
            self._state.pop(key, None)


# --------------------------------------------------------------------------
# F2 — TOTP (RFC 6238), standard library only
# --------------------------------------------------------------------------
def generate_totp_secret() -> str:
    """A new base32 TOTP secret (no padding), suitable for an authenticator."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    # base32 decode (pad back to a multiple of 8)
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32: str, code: str, *, window: int = 1, step: int = 30) -> bool:
    """True if `code` is valid now (± `window` steps to tolerate clock drift)."""
    if not secret_b32 or not code:
        return False
    code = str(code).strip().replace(" ", "")
    if not code.isdigit():
        return False
    counter = int(time.time() // step)
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + drift), code):
            return True
    return False


def totp_uri(secret_b32: str, account: str, issuer: str = "fastmodel") -> str:
    """otpauth:// URI an authenticator app can import (also rendered as a QR)."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")
