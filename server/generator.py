"""Assisted schedule generator (C1).

Greedy, fairness-aware filler that drafts a month given the staff roster, member
preferences, and accumulated history. It is deliberately *not* a full constraint
solver — it produces a sensible draft that the admin then edits in the Create grid.

Hard rules it never breaks:
  * only assign a location a person is qualified for (roster `clinics`);
  * never put a no-nights person on a night;
  * one worked shift per person per day.

Soft goals (greedy):
  * meet the daily coverage requirements (BC/HC day+night by default);
  * spread the load — prefer people with the fewest assignments so far (this run
    + historical), so nights/weekends don't always land on the same people;
  * honour member prefs (avoid their no-weekdays; favour prefer_nights for nights).

Output is the same `{person: {date: {level: code}}}` shape `create_schedule`
consumes, so a generated draft is identical in shape to a hand-built one.
"""

from __future__ import annotations

import datetime as dt

# Default per-day requirements: (location, level, count). Levels match
# create_schedule: "day" | "mid" | "night".
DEFAULT_REQUIREMENTS = [
    ("BC", "day", 1),
    ("BC", "night", 1),
    ("HC", "day", 1),
    ("HC", "night", 1),
]

# Clinics to try to staff on weekdays if qualified people are spare.
WEEKDAY_CLINICS = ["CV", "VLJ", "MOS", "RB", "ENC"]


def _dates(start: str, end: str) -> list[str]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out, cur = [], a
    while cur <= b:
        out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def _history_load(stats: dict | None) -> dict:
    """Total worked shifts per person across history (for fairness seeding)."""
    load: dict[str, int] = {}
    for name, c in (stats or {}).get("work", {}).items():
        load[name.upper()] = c.get("total", 0)
    return load


def generate(start: str, end: str, roster_quals: dict, *,
             prefs: dict | None = None, stats: dict | None = None,
             requirements=None, unavailable: dict | None = None,
             debt: dict | None = None) -> dict:
    """Return assignments {person: {date: {level: code}}} and a coverage report.

    `roster_quals` is {NAME: {clinics, works_nights, employment, seniority}}.
    `unavailable` is {NAME_UPPER: {dates}} a person must not be scheduled (e.g.
    approved vacation) — a hard block.
    `debt` is {NAME_UPPER: heavy-slot debt} added to a person's seed load so
    chronic night/weekend carriers are eased off next period (K3).
    """
    prefs = prefs or {}
    reqs = requirements or DEFAULT_REQUIREMENTS
    unavailable = unavailable or {}
    debt = debt or {}
    dates = _dates(start, end)

    # fairness counters: history load seeds it so chronic coverers start "ahead".
    load = _history_load(stats)
    people = list(roster_quals.keys())
    for n in people:
        load.setdefault(n, 0)
        load[n] += debt.get(n.upper(), 0)  # heavy-slot debt eases them off

    assignments: dict[str, dict] = {}
    last_day: dict[str, dt.date] = {}
    unfilled: list[dict] = []

    def _prefs_for(name):
        # prefs are keyed by the schedule name; try a few cases
        return prefs.get(name) or prefs.get(name.title()) or {}

    def eligible(name, loc, level, date, assigned_today):
        meta = roster_quals[name]
        if name in assigned_today:
            return False
        if date in unavailable.get(name.upper(), ()):
            return False  # hard block: approved vacation / explicitly unavailable
        if meta.get("clinics") and loc not in meta["clinics"]:
            return False
        if level == "night" and not meta.get("works_nights", True):
            return False
        wd = dt.date.fromisoformat(date).weekday()
        if wd in set(_prefs_for(name).get("no_weekdays") or []):
            return False
        return True

    def pick(loc, level, date, assigned_today):
        cands = [n for n in people if eligible(n, loc, level, date, assigned_today)]
        if not cands:
            return None

        def score(n):
            meta = roster_quals[n]
            pr = _prefs_for(n)
            s = -load[n] * 10  # fewer assignments => higher score (fairness)
            # spacing: penalise back-to-back days a little
            d = dt.date.fromisoformat(date)
            if last_day.get(n) and (d - last_day[n]).days <= 1:
                s -= 5
            if level == "night" and pr.get("prefer_nights"):
                s += 8
            if meta.get("employment") == "per_diem":
                s += 2  # flex pool slightly favoured
            return (s, -load[n], n)

        return max(cands, key=score)

    def assign(name, date, level, code):
        assignments.setdefault(name, {}).setdefault(date, {})[level] = code
        load[name] += 1
        last_day[name] = dt.date.fromisoformat(date)

    for date in dates:
        assigned_today: set[str] = set()
        for loc, level, count in reqs:
            for _ in range(count):
                who = pick(loc, level, date, assigned_today)
                if who is None:
                    unfilled.append({"date": date, "location": loc, "level": level})
                    continue
                assign(who, date, level, loc)
                assigned_today.add(who)
        # weekday clinics: fill if spare qualified people exist (best-effort)
        if dt.date.fromisoformat(date).weekday() < 5:
            for loc in WEEKDAY_CLINICS:
                who = pick(loc, "day", date, assigned_today)
                if who is not None:
                    assign(who, date, "day", loc)
                    assigned_today.add(who)

    report = {
        "people": len(assignments),
        "days": len(dates),
        "assigned": sum(len(d) for days in assignments.values() for d in days.values()),
        "unfilled": unfilled,
    }
    return {"assignments": assignments, "report": report}
