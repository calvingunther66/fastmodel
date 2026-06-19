"""User accounts: roles, capability toggles, and password hashing.

Stored in DATA_DIR/users.json so accounts persist across container rebuilds.
Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library, no extra deps).

Security extras (all stdlib): optional per-account TOTP 2FA (F2) and admin-issued
one-time password-reset codes (F3). Login-attempt throttling (F1) lives in
`server/security.py` and is wired in at the login route.

Roles:
  admin   — can do everything (all capabilities implicitly).
  member  — self-service; may be granted individual capabilities by an admin.

Capabilities (delegatable to members, one by one or in small groups):
  upload            — upload / re-parse schedules
  generate_schedule — use the assisted generator + templates (Create tab)
  manage_roster     — edit the staff roster (quals, nights, employment)
  manage_coverage   — mark anyone out, assign covers, run cascades, approve claims
  manage_swaps      — approve member shift swaps
  manage_users      — create / edit / delete accounts
  view_leaderboard  — see the step-up dashboard / equity board (Insights tab)
  tune_scoring      — adjust the fairness-vs-competence weight
  export            — download CSV / printable schedule exports
  automate          — use the automation API / MCP endpoint
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
import threading
from pathlib import Path

from .config import APP_PASSWORD, APP_USERNAME, DATA_DIR
from .security import generate_totp_secret, totp_uri, verify_totp

# How long an admin-issued password-reset code stays valid (F3).
RESET_CODE_TTL_SECONDS = 24 * 3600

CAPABILITIES = [
    "upload",             # upload / re-parse schedules
    "generate_schedule",  # assisted generator + templates (Create tab)
    "manage_roster",      # edit the staff roster (quals, nights, employment)
    "manage_coverage",    # mark out, assign covers, run cascades, approve claims
    "manage_swaps",       # approve member shift swaps
    "manage_users",       # create / edit / delete accounts + API tokens
    "view_leaderboard",   # see the step-up dashboard / equity board (Insights)
    "tune_scoring",       # adjust the fairness-vs-competence weight
    "export",             # download CSV / printable schedule exports
    "automate",           # use the automation API / MCP endpoint (ingest schedules)
]

# Convenience bundles the Users UI offers as one-click presets. Granting is still
# per-capability under the hood; these just select a small group at once.
CAPABILITY_PRESETS = {
    "Coordinator": ["manage_coverage", "manage_swaps"],
    "Scheduler": ["upload", "generate_schedule", "manage_roster"],
    "Analyst": ["view_leaderboard", "tune_scoring", "export"],
    "Automation": ["automate"],
}
ROLES = ["admin", "member"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt, hexhash = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


def has_cap(user: dict, cap: str) -> bool:
    return user.get("role") == "admin" or cap in (user.get("capabilities") or [])


def public_view(user: dict) -> dict:
    """User dict without the password hash, with effective capabilities."""
    caps = CAPABILITIES if user.get("role") == "admin" else (user.get("capabilities") or [])
    return {
        "username": user["username"],
        "role": user.get("role", "member"),
        "person": user.get("person"),
        "capabilities": caps,
        "protected": user.get("protected", False),
        "totp_enabled": bool(user.get("totp_enabled")),
        "reset_pending": bool(user.get("reset_code_hash")),
    }


class AccountStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.path = data_dir / "users.json"
        self._lock = threading.Lock()
        self._bootstrap()

    def _read(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"users": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def _bootstrap(self) -> None:
        """Ensure the env-configured admin always exists and matches the env
        password (so you can never lock yourself out)."""
        with self._lock:
            data = self._read()
            users = data.setdefault("users", [])
            env = next((u for u in users if u["username"] == APP_USERNAME), None)
            if env is None:
                users.append({
                    "username": APP_USERNAME,
                    "password_hash": hash_password(APP_PASSWORD),
                    "role": "admin", "person": None, "capabilities": [],
                    "protected": True, "created_at": _now(),
                })
            else:
                env["password_hash"] = hash_password(APP_PASSWORD)
                env["role"] = "admin"
                env["protected"] = True
            self._write(data)

    # ---- queries ----------------------------------------------------------
    def list(self) -> list[dict]:
        return self._read()["users"]

    def get(self, username: str) -> dict | None:
        return next((u for u in self.list() if u["username"] == username), None)

    def authenticate(self, username: str, password: str) -> dict | None:
        u = self.get(username)
        if u and verify_password(password, u["password_hash"]):
            return u
        return None

    # ---- mutations --------------------------------------------------------
    def create(self, username: str, password: str, role: str = "member",
               person: str | None = None, capabilities: list[str] | None = None) -> dict:
        username = username.strip()
        if not username or not password:
            raise ValueError("username and password are required")
        if role not in ROLES:
            raise ValueError("invalid role")
        caps = [c for c in (capabilities or []) if c in CAPABILITIES]
        with self._lock:
            data = self._read()
            if any(u["username"] == username for u in data["users"]):
                raise ValueError("username already exists")
            user = {
                "username": username, "password_hash": hash_password(password),
                "role": role, "person": person, "capabilities": caps,
                "protected": False, "created_at": _now(),
            }
            data["users"].append(user)
            self._write(data)
            return user

    def update(self, username: str, *, role=None, person=..., capabilities=None,
               password=None) -> dict:
        with self._lock:
            data = self._read()
            user = next((u for u in data["users"] if u["username"] == username), None)
            if user is None:
                raise KeyError(username)
            if role is not None:
                if role not in ROLES:
                    raise ValueError("invalid role")
                if user.get("protected") and role != "admin":
                    raise ValueError("the bootstrap admin must stay an admin")
                user["role"] = role
            if person is not ...:
                user["person"] = person
            if capabilities is not None:
                user["capabilities"] = [c for c in capabilities if c in CAPABILITIES]
            if password:
                user["password_hash"] = hash_password(password)
            self._write(data)
            return user

    def delete(self, username: str) -> None:
        with self._lock:
            data = self._read()
            user = next((u for u in data["users"] if u["username"] == username), None)
            if user is None:
                raise KeyError(username)
            if user.get("protected"):
                raise ValueError("the bootstrap admin cannot be deleted")
            data["users"] = [u for u in data["users"] if u["username"] != username]
            self._write(data)

    def _mutate(self, username: str, fn):
        """Run fn(user) inside the lock and persist; returns fn's result."""
        with self._lock:
            data = self._read()
            user = next((u for u in data["users"] if u["username"] == username), None)
            if user is None:
                raise KeyError(username)
            result = fn(user)
            self._write(data)
            return result

    # ---- password reset (F3): admin issues a one-time code, user redeems it --
    def issue_reset_code(self, username: str) -> str:
        """Mint a one-time reset code for `username` and return it (shown once).

        The admin hands the code to the member out-of-band; the member redeems
        it at the login screen to choose a new password. No email involved.
        """
        code = secrets.token_hex(4).upper()  # 8 hex chars, e.g. 'A1B2C3D4'

        def _set(user):
            user["reset_code_hash"] = hash_password(code)
            user["reset_expires"] = dt.datetime.now(dt.timezone.utc).timestamp() + RESET_CODE_TTL_SECONDS
            return None

        self._mutate(username, _set)
        return code

    def redeem_reset(self, username: str, code: str, new_password: str) -> dict:
        """Redeem a reset code and set a new password. Raises ValueError on
        invalid/expired codes (same message either way, to avoid leaking which)."""
        if not new_password:
            raise ValueError("a new password is required")

        def _redeem(user):
            stored = user.get("reset_code_hash")
            expires = user.get("reset_expires") or 0
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            if not stored or now > expires or not verify_password(code or "", stored):
                raise ValueError("invalid or expired reset code")
            user["password_hash"] = hash_password(new_password)
            user.pop("reset_code_hash", None)
            user.pop("reset_expires", None)
            return user

        return self._mutate(username, _redeem)

    # ---- TOTP 2FA (F2): optional per-account, off by default -----------------
    def begin_totp(self, username: str) -> dict:
        """Generate (but don't yet enable) a TOTP secret; return enrollment info.

        Enrollment isn't active until `enable_totp` confirms a valid code, so a
        half-finished enrollment can never lock anyone out."""
        secret = generate_totp_secret()
        user = self.get(username)
        if user is None:
            raise KeyError(username)

        def _set(u):
            u["totp_pending_secret"] = secret
            u["totp_enabled"] = bool(u.get("totp_enabled"))  # unchanged
            return None

        self._mutate(username, _set)
        return {"secret": secret, "otpauth_uri": totp_uri(secret, username)}

    def enable_totp(self, username: str, code: str) -> None:
        """Confirm enrollment by verifying a code against the pending secret."""
        def _enable(user):
            secret = user.get("totp_pending_secret")
            if not secret:
                raise ValueError("start 2FA enrollment first")
            if not verify_totp(secret, code):
                raise ValueError("that code didn't match — check your authenticator app")
            user["totp_secret"] = secret
            user["totp_enabled"] = True
            user.pop("totp_pending_secret", None)
            return None

        self._mutate(username, _enable)

    def disable_totp(self, username: str) -> None:
        def _disable(user):
            user.pop("totp_secret", None)
            user.pop("totp_pending_secret", None)
            user["totp_enabled"] = False
            return None

        self._mutate(username, _disable)

    def verify_totp_code(self, user: dict, code: str) -> bool:
        return verify_totp(user.get("totp_secret") or "", code or "")
