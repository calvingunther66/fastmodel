"""Server configuration, read from environment with sensible local defaults.

Override these in production (e.g. on the Raspberry Pi) via environment
variables or a .env file:

    APP_USERNAME   shared login username           (default: admin)
    APP_PASSWORD   shared login password           (default: changeme)
    SECRET_KEY     session-cookie signing key      (default: random per start)
    DATA_DIR       where uploads/tokens are stored (default: ./data)
    TIMEZONE       Olson tz for calendar events    (default: America/Los_Angeles)
    PUBLIC_BASE_URL  external URL for .ics links    (default: derived from request)
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
TIMEZONE = os.environ.get("TIMEZONE", "America/Los_Angeles")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

DATA_DIR.mkdir(parents=True, exist_ok=True)

USING_DEFAULT_PASSWORD = APP_PASSWORD == "changeme"
