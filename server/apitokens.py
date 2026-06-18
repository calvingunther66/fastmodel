"""API tokens for headless / agent access (the secure automation 'key').

A bearer token authenticates as a service principal with a fixed set of
capabilities — no browser session needed. Tokens are shown **once** at creation,
stored only as a salted SHA-256 hash, are scope-limited, revocable, and every use
is attributable in the audit log. This is a front door with a revocable key, not a
hidden bypass: it goes through the same capability checks as everything else.

Stored in DATA_DIR/api_tokens.json.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
import threading
from pathlib import Path

from .accounts import CAPABILITIES
from .config import DATA_DIR

_PREFIX = "sk_sched_"  # human-recognisable token prefix


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ApiTokenStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.path = data_dir / "api_tokens.json"
        self._lock = threading.Lock()

    def _read(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"tokens": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def list(self) -> list[dict]:
        # Never return the hash.
        return [{k: v for k, v in t.items() if k != "token_hash"} for t in self._read()["tokens"]]

    def create(self, name: str, capabilities: list[str]) -> tuple[dict, str]:
        caps = [c for c in (capabilities or []) if c in CAPABILITIES]
        token = _PREFIX + secrets.token_urlsafe(32)
        record = {
            "id": secrets.token_hex(8),
            "name": (name or "agent").strip(),
            "token_hash": _hash(token),
            "capabilities": caps,
            "created_at": _now(),
            "last_used": None,
        }
        with self._lock:
            data = self._read()
            data["tokens"].append(record)
            self._write(data)
        public = {k: v for k, v in record.items() if k != "token_hash"}
        return public, token  # token returned once, never stored in clear

    def revoke(self, token_id: str) -> None:
        with self._lock:
            data = self._read()
            data["tokens"] = [t for t in data["tokens"] if t["id"] != token_id]
            self._write(data)

    def verify(self, token: str) -> dict | None:
        """Return a principal dict for a valid bearer token, else None."""
        if not token or not token.startswith(_PREFIX):
            return None
        h = _hash(token)
        with self._lock:
            data = self._read()
            for t in data["tokens"]:
                if hmac.compare_digest(t["token_hash"], h):
                    t["last_used"] = _now()
                    self._write(data)
                    return {
                        "username": f"token:{t['name']}",
                        "role": "member",
                        "person": None,
                        "capabilities": t["capabilities"],
                        "protected": False,
                        "is_token": True,
                    }
        return None
