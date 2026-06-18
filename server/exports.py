"""CSV exports (D2). A printable month view is the browser's "print to PDF" on the
schedule grid, so no PDF dependency is needed here."""

from __future__ import annotations

import csv
import io


def _rows_for(person: dict):
    for s in person.get("shifts", []):
        yield {
            "date": s.get("date"),
            "shift_type": s.get("shift_type"),
            "code": s.get("code"),
            "meaning": s.get("meaning") or "",
            "start": s.get("start") or "",
            "end": s.get("end") or "",
            "available": "" if s.get("available", True) else "called out",
            "covering_for": s.get("covering_for") or "",
        }


def schedule_csv(schedule: dict) -> str:
    """One row per (person, shift) across the whole team."""
    buf = io.StringIO()
    cols = ["person", "date", "shift_type", "code", "meaning", "start", "end",
            "available", "covering_for"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for p in schedule.get("people", []):
        name = p.get("name")
        if not name:
            continue
        for row in _rows_for(p):
            w.writerow({"person": name, **row})
    return buf.getvalue()


def person_csv(schedule: dict, name: str) -> str | None:
    """Per-person CSV, or None if the person isn't on the schedule."""
    person = next((p for p in schedule.get("people", []) if p.get("name") == name), None)
    if person is None:
        return None
    buf = io.StringIO()
    cols = ["date", "shift_type", "code", "meaning", "start", "end", "available",
            "covering_for"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for row in _rows_for(person):
        w.writerow(row)
    return buf.getvalue()
