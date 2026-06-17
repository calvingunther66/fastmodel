"""Persistence for the uploaded schedule and per-person calendar tokens.

State lives in DATA_DIR:
  current.xlsx   the most recently uploaded workbook (raw bytes)
  schedule.json  the parsed result + metadata (which sheet, when, sheet list)
  tokens.json    stable {person_name: secret_token} used for live .ics URLs

Tokens are kept stable across re-uploads so a person's subscribed calendar link
never breaks when a new schedule is posted.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import threading
from pathlib import Path

import openpyxl

from schedule_extractor.roster_extractor import extract_roster

from .config import DATA_DIR


class ScheduleStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.xlsx_path = data_dir / "current.xlsx"
        self.schedule_path = data_dir / "schedule.json"
        self.tokens_path = data_dir / "tokens.json"
        self._lock = threading.Lock()

    # ---- low-level json helpers ------------------------------------------
    def _read_json(self, path: Path, default):
        if path.exists():
            return json.loads(path.read_text())
        return default

    def _write_json(self, path: Path, data) -> None:
        path.write_text(json.dumps(data, indent=2, default=str))

    # ---- parsing ----------------------------------------------------------
    def _parse(self, sheet_name: str | None):
        wb = openpyxl.load_workbook(self.xlsx_path, data_only=True)
        sheets = wb.sheetnames
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            # Auto-pick by (named people, total shifts); on a tie prefer the
            # right-most sheet, since final/clean versions tend to sit last.
            best_score, ws = (-1, -1, -1), wb.worksheets[0]
            for index, cand in enumerate(wb.worksheets):
                try:
                    parsed = extract_roster(cand)
                    named = sum(1 for p in parsed["people"] if p["name"])
                    total = sum(len(p["shifts"]) for p in parsed["people"])
                except Exception:
                    named = total = -1
                score = (named, total, index)
                if score > best_score:
                    best_score, ws = score, cand
        result = extract_roster(ws)
        result["available_sheets"] = sheets
        result["parsed_sheet"] = ws.title
        result["uploaded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        return result

    # ---- public API -------------------------------------------------------
    def ingest(self, xlsx_bytes: bytes, sheet_name: str | None = None) -> dict:
        """Store a freshly uploaded workbook and parse it."""
        with self._lock:
            self.xlsx_path.write_bytes(xlsx_bytes)
            result = self._parse(sheet_name)
            self._write_json(self.schedule_path, result)
            self._ensure_tokens(result)
            return result

    def reparse(self, sheet_name: str) -> dict:
        """Re-parse the already-uploaded workbook with a specific sheet."""
        with self._lock:
            if not self.xlsx_path.exists():
                raise FileNotFoundError("no workbook uploaded yet")
            result = self._parse(sheet_name)
            self._write_json(self.schedule_path, result)
            self._ensure_tokens(result)
            return result

    def get_schedule(self) -> dict | None:
        return self._read_json(self.schedule_path, None)

    def _tokens(self) -> dict:
        return self._read_json(self.tokens_path, {})

    def _ensure_tokens(self, schedule: dict) -> None:
        tokens = self._tokens()
        changed = False
        for person in schedule.get("people", []):
            name = person.get("name")
            if name and name not in tokens:
                tokens[name] = secrets.token_urlsafe(16)
                changed = True
        if changed:
            self._write_json(self.tokens_path, tokens)

    def people_with_tokens(self) -> list[dict]:
        schedule = self.get_schedule() or {}
        tokens = self._tokens()
        out = []
        for person in schedule.get("people", []):
            name = person.get("name")
            if not name:
                continue
            out.append({
                "name": name,
                "token": tokens.get(name),
                "shift_count": len(person.get("shifts", [])),
            })
        return out

    def person_by_token(self, token: str) -> dict | None:
        tokens = self._tokens()
        name = next((n for n, t in tokens.items() if t == token), None)
        if not name:
            return None
        schedule = self.get_schedule() or {}
        for person in schedule.get("people", []):
            if person.get("name") == name:
                return person
        return {"name": name, "shifts": []}  # known person, not in current schedule
