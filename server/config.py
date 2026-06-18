"""Server configuration, read from environment with sensible local defaults.

Override these in production (e.g. on the Raspberry Pi) via environment
variables or a .env file:

    APP_USERNAME   bootstrap admin username        (default: admin)
    APP_PASSWORD   bootstrap admin password        (default: changeme)
    SECRET_KEY     session-cookie signing key      (default: persisted in DATA_DIR)
    DATA_DIR       where all state is stored        (default: ./data)
    TIMEZONE       Olson tz for calendar events    (default: America/Los_Angeles)
    PUBLIC_BASE_URL  external URL for .ics links    (default: derived from request)
    SESSION_HTTPS_ONLY  mark the cookie Secure       (default: false)

The bootstrap admin (APP_USERNAME/APP_PASSWORD) is always re-synced on startup so
you can never be locked out. All other accounts and data live in DATA_DIR, which
should be a persistent volume so accounts/history/data survive rebuilds.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")
DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
TIMEZONE = os.environ.get("TIMEZONE", "America/Los_Angeles")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# Where the automation looks for spreadsheets to ingest (sync your .xlsx here).
INBOX_DIR = Path(os.environ.get("INBOX_DIR", str(DATA_DIR / "inbox"))).resolve()
INBOX_DIR.mkdir(parents=True, exist_ok=True)

# Optional built-in scheduler: "off" (default), "daily", "weekly", or seconds.
AUTO_INGEST = os.environ.get("AUTO_INGEST", "off").strip().lower()

# Mark the session cookie Secure (HTTPS-only). Turn on when served over HTTPS,
# e.g. behind a Cloudflare tunnel: SESSION_HTTPS_ONLY=true
SESSION_HTTPS_ONLY = os.environ.get("SESSION_HTTPS_ONLY", "false").lower() in (
    "1", "true", "yes", "on",
)


def _resolve_secret_key() -> str:
    """Use SECRET_KEY if set, else persist a generated one in DATA_DIR so that
    logins survive restarts and container rebuilds without extra configuration."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    key_file = DATA_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return key


SECRET_KEY = _resolve_secret_key()
USING_DEFAULT_PASSWORD = APP_PASSWORD == "changeme"
