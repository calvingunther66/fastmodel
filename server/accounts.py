"""User accounts: roles, capability toggles, and password hashing.

Stored in DATA_DIR/users.json so accounts persist across container rebuilds.
Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library, no extra deps).

Roles:
  admin   — can do everything (all capabilities implicitly).
  member  — self-service; may be granted individual capabilities by an admin.

Capabilities (delegatable to members):
  upload           — upload / re-parse schedules
  manage_coverage  — mark anyone out, assign covers, run cascades
  manage_users     — create / edit / delete accounts
  view_leaderboard — see the step-up dashboard (Insights tab)
  tune_scoring     — adjust the fairness-vs-competence weight
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

CAPABILITIES = [
    "upload",            # upload / re-parse schedules
    "manage_coverage",   # mark out, assign covers, run cascades
    "manage_users",      # create / edit / delete accounts
    "view_leaderboard",  # see the step-up dashboard (Insights)
    "tune_scoring",      # adjust the fairness-vs-competence weight
]
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
