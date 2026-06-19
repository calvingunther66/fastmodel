"""Coverage gap forecaster (K2).

Looks at the active schedule against the daily coverage requirements and flags
days that are at risk *before* they arrive:

  * **gap**  — a required slot is under-staffed (fewer people than needed).
  * **thin** — a required slot is met exactly, but nobody free that day is
    qualified to step in if someone drops out (a single point of failure).

It reuses the coverage engine's profiles/qualification helpers and the
generator's default requirements, so "qualified" and "required" mean the same
thing across the app.
"""

from __future__ import annotations

import datetime as dt

from .coverage import (_day_state, _entries_on, _meta, _profiles, _qualified_for)
from .generator import DEFAULT_REQUIREMENTS

_LEVEL_TO_TYPE = {"day": "day", "mid": "midshift", "night": "night"}


def _dates(schedule: dict) -> list[str]:
    dr = schedule.get("date_range") or {}
    start, end = dr.get("start"), dr.get("end")
    if not (start and end):
        # derive from shifts if no explicit range
        all_d = sorted({s["date"] for p in schedule.get("people", [])
                        for s in p.get("shifts", []) if s.get("date")})
        return all_d
    out, cur = [], dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    while cur <= last:
        out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def _scheduled_count(schedule, date, loc, stype) -> int:
    n = 0
    for p in schedule.get("people", []):
        for s in p.get("shifts", []):
            if (s.get("date") == date and s.get("category") == "location"
                    and (s.get("code") or "").upper() == loc
                    and s.get("shift_type") == stype and s.get("available", True)):
                n += 1
    return n


def _free_qualified(schedule, date, loc, stype, profiles, roster) -> int:
    """How many people are free/available that day AND qualified for the slot."""
    is_night = stype == "night"
    n = 0
    for p in schedule.get("people", []):
        name = p.get("name")
        if not name:
            continue
        state, _ = _day_state(_entries_on(p, date))
        if state not in ("available", "free"):
            continue
        meta = _meta(roster, name)
        if is_night and meta is not None and not meta.get("works_nights", True):
            continue
        prof = profiles.get(name, {"codes": set(), "nights": False})
        if _qualified_for(loc, prof, meta):
            n += 1
    return n


def forecast(schedule: dict, requirements=None, roster=None,
             today: str | None = None) -> dict:
    """Return per-day coverage risk for upcoming dates."""
    reqs = requirements or DEFAULT_REQUIREMENTS
    profiles = _profiles(schedule)
    today = today or dt.date.today().isoformat()

    days = []
    gap_days = thin_days = 0
    for date in _dates(schedule):
        if date < today:
            continue  # only forecast upcoming risk
        issues = []
        for loc, level, need in reqs:
            stype = _LEVEL_TO_TYPE.get(level, "day")
            have = _scheduled_count(schedule, date, loc, stype)
            if have < need:
                issues.append({"location": loc, "level": level, "severity": "gap",
                               "have": have, "need": need,
                               "message": f"{loc} {level}: {have}/{need} scheduled"})
            elif have == need:
                backup = _free_qualified(schedule, date, loc, stype, profiles, roster)
                if backup == 0:
                    issues.append({"location": loc, "level": level, "severity": "thin",
                                   "have": have, "need": need, "backup": 0,
                                   "message": f"{loc} {level}: met but no qualified backup free"})
        if not issues:
            continue
        risk = "gap" if any(i["severity"] == "gap" for i in issues) else "thin"
        if risk == "gap":
            gap_days += 1
        else:
            thin_days += 1
        days.append({"date": date, "risk": risk, "issues": issues})

    return {"days": days, "summary": {"gap_days": gap_days, "thin_days": thin_days,
                                      "evaluated_from": today}}
