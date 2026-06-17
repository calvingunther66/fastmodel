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
from .coverage import apply_overrides, find_open_shift


class ScheduleStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.xlsx_path = data_dir / "current.xlsx"
        self.schedule_path = data_dir / "schedule.json"
        self.tokens_path = data_dir / "tokens.json"
        self.overrides_path = data_dir / "overrides.json"
        self.contacts_path = data_dir / "contacts.json"
        self.offers_path = data_dir / "availability.json"
        self.stats_path = data_dir / "stats.json"
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
            self._record_work(result)
            return result

    def reparse(self, sheet_name: str) -> dict:
        """Re-parse the already-uploaded workbook with a specific sheet."""
        with self._lock:
            if not self.xlsx_path.exists():
                raise FileNotFoundError("no workbook uploaded yet")
            result = self._parse(sheet_name)
            self._write_json(self.schedule_path, result)
            self._ensure_tokens(result)
            self._record_work(result)
            return result

    def get_raw_schedule(self) -> dict | None:
        """The parsed schedule as stored, without call-out overrides applied."""
        return self._read_json(self.schedule_path, None)

    def get_schedule(self) -> dict | None:
        """The schedule with call-outs flagged, covers injected, contact overrides
        applied. Always a fresh copy (safe to mutate by callers)."""
        base = self._read_json(self.schedule_path, None)
        if base is None:
            return None
        sched = apply_overrides(base, self._callouts())  # deep-copies even if empty
        contacts = self._contacts()
        if contacts:
            for p in sched.get("people", []):
                if p.get("name") in contacts:
                    p["contact"] = contacts[p["name"]]
        return sched

    # ---- contact overrides (members edit their own) ----------------------
    def _contacts(self) -> dict:
        return self._read_json(self.contacts_path, {})

    def set_contact(self, person: str, lines: list[str]) -> None:
        with self._lock:
            contacts = self._contacts()
            contacts[person] = [str(line).strip() for line in lines if str(line).strip()]
            self._write_json(self.contacts_path, contacts)

    # ---- availability offers (people offering to cover) ------------------
    def _offers(self) -> list[dict]:
        return self._read_json(self.offers_path, {}).get("offers", [])

    def list_offers(self) -> list[dict]:
        return self._offers()

    def add_offer(self, person: str, date: str, note: str = "") -> None:
        with self._lock:
            offers = self._offers()
            if not any(o["person"] == person and o["date"] == date for o in offers):
                offers.append({"person": person, "date": date, "note": note})
                self._write_json(self.offers_path, {"offers": offers})

    def remove_offer(self, person: str, date: str) -> None:
        with self._lock:
            offers = [o for o in self._offers()
                      if not (o["person"] == person and o["date"] == date)]
            self._write_json(self.offers_path, {"offers": offers})

    def offers_for_date(self, date: str) -> set[str]:
        return {o["person"] for o in self._offers() if o["date"] == date}

    # ---- adaptive stats: work frequency + cover step-ups -----------------
    def _stats(self) -> dict:
        return self._read_json(self.stats_path, {"work_by_period": {}, "covers": {}})

    def _record_work(self, result: dict) -> None:
        """Fold this schedule period's worked-shift counts into the stats store.

        Keyed by period so re-parsing the same period replaces (not double-counts);
        distinct periods accumulate, so the picture sharpens as more are uploaded.
        """
        # Key by the schedule's date range so re-parsing the same period (e.g.
        # switching from a draft sheet to the final one) replaces rather than
        # double-counts; genuinely new periods accumulate.
        dr = result.get("date_range", {}) or {}
        period = f"{dr.get('start')}..{dr.get('end')}"
        counts: dict = {}
        for p in result.get("people", []):
            name = p.get("name")
            if not name:
                continue
            by_code, by_type, total = {}, {}, 0
            for s in p["shifts"]:
                if s.get("category") == "location":
                    code = s["code"].upper()
                    st = s["shift_type"]
                    by_code[code] = by_code.get(code, 0) + 1
                    by_type[st] = by_type.get(st, 0) + 1
                    total += 1
            if total:
                counts[name] = {"by_code": by_code, "by_type": by_type, "total": total}
        stats = self._stats()
        stats["work_by_period"][period] = counts
        self._write_json(self.stats_path, stats)

    def _bump_cover(self, person: str, code: str | None, shift_type: str) -> None:
        stats = self._stats()
        c = stats.setdefault("covers", {}).setdefault(
            person, {"count": 0, "by_code": {}, "by_type": {}})
        c["count"] += 1
        if code:
            c["by_code"][code.upper()] = c["by_code"].get(code.upper(), 0) + 1
        if shift_type:
            c["by_type"][shift_type] = c["by_type"].get(shift_type, 0) + 1
        self._write_json(self.stats_path, stats)

    def aggregated_stats(self) -> dict:
        """Per-person totals across all periods, plus cover step-up counts."""
        stats = self._stats()
        work: dict = {}
        for counts in stats.get("work_by_period", {}).values():
            for name, c in counts.items():
                w = work.setdefault(name, {"by_code": {}, "by_type": {}, "total": 0})
                for k, v in c["by_code"].items():
                    w["by_code"][k] = w["by_code"].get(k, 0) + v
                for k, v in c["by_type"].items():
                    w["by_type"][k] = w["by_type"].get(k, 0) + v
                w["total"] += c["total"]
        return {
            "work": work,
            "covers": stats.get("covers", {}),
            "periods": len(stats.get("work_by_period", {})),
        }

    def leaderboard(self) -> dict:
        """Per-person insights ranked by who has stepped up to cover the most."""
        agg = self.aggregated_stats()
        covers, work = agg["covers"], agg["work"]
        names = set(covers) | set(work)
        # Include everyone currently on the schedule, even with zero history.
        sched = self.get_raw_schedule() or {}
        names |= {p["name"] for p in sched.get("people", []) if p.get("name")}
        rows = []
        for n in sorted(names):
            c = covers.get(n, {})
            w = work.get(n, {})
            rows.append({
                "name": n,
                "covers": c.get("count", 0),
                "covers_by_type": c.get("by_type", {}),
                "covers_by_code": c.get("by_code", {}),
                "worked_total": w.get("total", 0),
                "worked_by_code": w.get("by_code", {}),
            })
        rows.sort(key=lambda r: (-r["covers"], -r["worked_total"], r["name"]))
        return {"periods": agg["periods"], "people": rows}

    # ---- call-out overrides ----------------------------------------------
    def _callouts(self) -> list[dict]:
        return self._read_json(self.overrides_path, {}).get("callouts", [])

    def _save_callouts(self, callouts: list[dict]) -> None:
        self._write_json(self.overrides_path, {"callouts": callouts})

    @staticmethod
    def _same(co: dict, name: str, date: str, shift_type: str) -> bool:
        return co["name"] == name and co["date"] == date and co["shift_type"] == shift_type

    def list_callouts(self) -> list[dict]:
        return self._callouts()

    def mark_sick(self, name: str, date: str, shift_type: str, code: str | None = None,
                  reason: str = "out sick") -> None:
        with self._lock:
            callouts = self._callouts()
            if not any(self._same(c, name, date, shift_type) for c in callouts):
                callouts.append({
                    "name": name, "date": date, "shift_type": shift_type,
                    "code": code, "reason": reason, "covered_by": None,
                })
                self._save_callouts(callouts)

    def assign_cover(self, name: str, date: str, shift_type: str, covered_by: str,
                     code: str | None = None) -> None:
        with self._lock:
            callouts = self._callouts()
            for c in callouts:
                if self._same(c, name, date, shift_type):
                    c["covered_by"] = covered_by
                    code = code or c.get("code")
                    break
            else:
                callouts.append({
                    "name": name, "date": date, "shift_type": shift_type,
                    "code": code, "reason": "out sick", "covered_by": covered_by,
                })
            self._save_callouts(callouts)
            # Record the step-up so the scorer learns who reliably covers.
            if code is None:
                shift = find_open_shift(self.get_raw_schedule() or {}, name, date, shift_type)
                code = (shift or {}).get("code")
            self._bump_cover(covered_by, code, shift_type)

    def assign_cascade(self, name: str, date: str, shift_type: str,
                       mover: str, from_code: str | None, from_type: str,
                       backfill: str) -> None:
        """Apply a two-step cascade: mover covers the open shift, a free person
        backfills the mover's vacated slot."""
        # 1) mover covers the open (sick) shift
        self.assign_cover(name, date, shift_type, mover)
        # 2) the mover's own slot becomes a call-out, backfilled by `backfill`
        self.mark_sick(mover, date, from_type, code=from_code,
                       reason=f"moved to cover {name}")
        self.assign_cover(mover, date, from_type, backfill, code=from_code)

    def clear_callout(self, name: str, date: str, shift_type: str) -> None:
        with self._lock:
            callouts = [c for c in self._callouts()
                        if not self._same(c, name, date, shift_type)]
            self._save_callouts(callouts)

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
