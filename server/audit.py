"""Append-only activity log.

Records who did what and when to DATA_DIR/audit.jsonl (one JSON object per line,
which keeps appends cheap and the file easy to tail/back up). Admins can view the
most recent entries via /api/audit.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

from .config import DATA_DIR


class AuditLog:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.path = data_dir / "audit.jsonl"
        self._lock = threading.Lock()

    def log(self, actor: str, action: str, details: dict | None = None) -> None:
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "details": details or {},
        }
        line = json.dumps(entry, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def tail(self, n: int = 200) -> list[dict]:
        """Most recent entries first."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out[::-1]

    # Detail keys whose values name a schedule person (for the personal feed, J1).
    _PERSON_KEYS = ("name", "person", "covered_by", "mover", "backfill",
                    "claimer", "a_person", "b_person", "with")

    def for_person(self, person: str, scan: int = 1000) -> list[dict]:
        """Most-recent-first entries that affect `person` (J1).

        Matches the person against the people-naming fields of each entry's
        details, so it surfaces things done *to* them (covered, moved, vacation
        decided, swap accepted) regardless of who performed the action."""
        if not person:
            return []
        target = person.strip().lower()
        out = []
        for entry in self.tail(scan):
            details = entry.get("details") or {}
            values = {str(details.get(k, "")).strip().lower() for k in self._PERSON_KEYS}
            if target in values:
                out.append(entry)
        return out
