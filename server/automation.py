"""Autonomous ingestion: watch an inbox of spreadsheets and feed in the latest.

Workflow: the owner syncs their Excel files into INBOX_DIR (via Google Drive
desktop sync, rclone, Syncthing, scp, …). The automation finds the newest `.xlsx`,
and ingests it — but idempotently:

  * unchanged  — same content hash as last time -> no-op.
  * updated    — same schedule period as the active one, new content -> replaces.
  * added      — a new period (date range we haven't seen) -> becomes active.

State (seen hashes + periods) lives in DATA_DIR/automation_state.json so repeated
runs are safe to schedule daily/weekly.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .config import INBOX_DIR


class Automation:
    def __init__(self, store, inbox: Path = INBOX_DIR) -> None:
        self.store = store
        self.inbox = inbox
        self.state_path = store.data_dir / "automation_state.json"

    # ---- state ------------------------------------------------------------
    def _state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"seen_hashes": [], "periods": [], "last": None}

    def _save(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, default=str))

    # ---- inbox ------------------------------------------------------------
    def list_spreadsheets(self) -> list[dict]:
        files = []
        for p in sorted(self.inbox.glob("*.xls*")):
            if p.name.startswith("~$"):  # Excel lock files
                continue
            st = p.stat()
            files.append({
                "name": p.name,
                "size": st.st_size,
                "modified": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
            })
        files.sort(key=lambda f: f["modified"], reverse=True)
        return files

    def _latest_path(self) -> Path | None:
        candidates = [p for p in self.inbox.glob("*.xls*") if not p.name.startswith("~$")]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def status(self) -> dict:
        s = self._state()
        return {
            "inbox": str(self.inbox),
            "spreadsheets": len(self.list_spreadsheets()),
            "periods_ingested": s.get("periods", []),
            "last": s.get("last"),
        }

    def inspect_latest(self) -> dict:
        """Parse the newest file per sheet (without storing) so an agent can pick
        the right tab before ingesting."""
        path = self._latest_path()
        if path is None:
            return {"status": "empty", "detail": f"no spreadsheets in {self.inbox}"}
        import openpyxl

        from schedule_extractor.roster_extractor import extract_roster
        from .store import is_draft_sheet

        wb = openpyxl.load_workbook(path, data_only=True)
        sheets, best = [], None
        for ws in wb.worksheets:
            try:
                r = extract_roster(ws)
                people = sum(1 for p in r["people"] if p.get("name"))
                info = {"name": ws.title, "people": people,
                        "date_range": r.get("date_range"),
                        "draft": is_draft_sheet(ws.title)}
            except Exception as exc:  # noqa: BLE001
                info = {"name": ws.title, "people": 0, "error": str(exc), "draft": True}
            sheets.append(info)
            key = (info["people"], 0 if info["draft"] else 1)
            if best is None or key > best[0]:
                best = (key, ws.title)
        return {"status": "ok", "file": path.name, "sheets": sheets,
                "suggested_sheet": best[1] if best else None}

    # ---- the autonomous action -------------------------------------------
    def ingest_latest(self, *, sheet: str | None = None, actor: str = "automation") -> dict:
        path = self._latest_path()
        if path is None:
            return {"status": "empty", "detail": f"no spreadsheets in {self.inbox}"}

        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        state = self._state()

        # Skip re-ingesting an identical file — unless a specific sheet is named,
        # so an agent can correct the tab after an auto-pick.
        if digest in state.get("seen_hashes", []) and not sheet:
            return {"status": "unchanged", "file": path.name,
                    "detail": "this exact file was already ingested"}

        result = self.store.ingest(data, sheet_name=sheet)
        period = f"{result.get('date_range', {}).get('start')}..{result.get('date_range', {}).get('end')}"
        is_new_period = period not in state.get("periods", [])

        if digest not in state.setdefault("seen_hashes", []):
            state["seen_hashes"].append(digest)
        state["seen_hashes"] = state["seen_hashes"][-50:]  # keep recent
        if is_new_period:
            state.setdefault("periods", []).append(period)
        state["last"] = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "file": path.name, "period": period,
            "status": "added" if is_new_period else "updated",
            "by": actor,
        }
        self._save(state)

        return {
            "status": "added" if is_new_period else "updated",
            "file": path.name,
            "sheet": result.get("parsed_sheet"),
            "available_sheets": result.get("available_sheets", []),
            "period": period,
            "people": len([p for p in result.get("people", []) if p.get("name")]),
        }
