"""Schedule validator / linter (A2) + fatigue checks (A3).

Runs over a parsed/created schedule and surfaces problems an admin should see
*before* trusting it: people assigned where they aren't qualified, no-nights staff
put on nights, double-bookings, understaffed days, unknown codes, and fatigue
patterns (too many consecutive shifts, not enough rest between night and day,
excessive weekly hours).

All checks are advisory — they return a list of issues, never raise. When the real
roster isn't loaded yet (`roster` is None) the qualification/no-nights checks are
skipped (we can't know), so nothing false-alarms pre-roster.
"""

from __future__ import annotations

import datetime as dt

# Daily coverage minimums (how many people must be on each location/level per day).
# Empty by default: the real workbook is availability-oriented (lots of A/V/R/H,
# few explicit location assignments), so hardcoded BC/HC minimums would flag nearly
# every day as "understaffed". Callers that build full location schedules can pass
# minimums={("BC","day"):1, ...} to turn the check on.
DEFAULT_MINIMUMS: dict = {}

# Codes the owner told us to leave undefined — never flag them as "unknown".
IGNORED_UNKNOWN = {"*", "UL"}

# Fatigue thresholds.
MAX_CONSECUTIVE_DAYS = 6        # worked days in a row before we flag it
MIN_REST_HOURS = 10            # rest between the end of one shift and the next start
MAX_HOURS_PER_7 = 60          # worked hours in any rolling 7-day window


def _issue(severity, kind, message, person=None, date=None, shift_type=None):
    return {"severity": severity, "kind": kind, "message": message,
            "person": person, "date": date, "shift_type": shift_type}


def _to_minutes(hhmm: str | None) -> int | None:
    if not hhmm or ":" not in hhmm:
        return None
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def shift_hours(s: dict) -> float:
    """Duration of a timed shift in hours (0 for status/all-day markers)."""
    start, end = _to_minutes(s.get("start")), _to_minutes(s.get("end"))
    if start is None or end is None:
        return 0.0
    span = end - start
    if s.get("crosses_midnight") or span <= 0:
        span += 24 * 60
    return round(span / 60.0, 2)


def _start_dt(s: dict) -> dt.datetime | None:
    mins = _to_minutes(s.get("start"))
    if mins is None:
        return None
    try:
        d = dt.date.fromisoformat(s["date"])
    except (ValueError, KeyError, TypeError):
        return None
    return dt.datetime(d.year, d.month, d.day, mins // 60, mins % 60)


def _end_dt(s: dict) -> dt.datetime | None:
    start = _start_dt(s)
    if start is None:
        return None
    return start + dt.timedelta(hours=shift_hours(s))


def _meta(roster, name):
    if not roster:
        return None
    return roster.get((name or "").upper())


def validate_schedule(schedule: dict, roster: dict | None = None,
                      prefs: dict | None = None,
                      minimums: dict | None = None) -> list[dict]:
    """Return a list of advisory issues for the schedule."""
    if not schedule:
        return []
    issues: list[dict] = []
    mins = {**DEFAULT_MINIMUMS, **(minimums or {})}
    prefs = prefs or {}
    coverage: dict[tuple, int] = {}

    for p in schedule.get("people", []):
        name = p.get("name")
        if not name:
            continue
        meta = _meta(roster, name)
        worked = [s for s in p.get("shifts", []) if s.get("category") == "location"]

        # double-booking: two worked shifts on the same date + level
        seen: dict[tuple, str] = {}
        for s in worked:
            key = (s["date"], s["shift_type"])
            if key in seen:
                issues.append(_issue(
                    "error", "double_booked",
                    f"{name} is double-booked on {s['date']} ({s['shift_type']}): "
                    f"{seen[key]} and {s.get('code')}",
                    name, s["date"], s["shift_type"]))
            else:
                seen[key] = s.get("code")

        for s in p.get("shifts", []):
            code = (s.get("code") or "").upper()
            # unknown code (skip the ones the owner said to ignore)
            if s.get("category") == "unknown" and (s.get("code") or "").strip() not in IGNORED_UNKNOWN:
                issues.append(_issue(
                    "warning", "unknown_code",
                    f"{name} has an unrecognised code “{s.get('code')}” on {s['date']}",
                    name, s["date"], s.get("shift_type")))
            if s.get("category") != "location":
                continue
            # count toward coverage minimums
            coverage[(s["date"], code, s["shift_type"])] = \
                coverage.get((s["date"], code, s["shift_type"]), 0) + 1
            # qualification (roster only)
            if meta is not None and meta.get("clinics") and code not in meta["clinics"]:
                issues.append(_issue(
                    "error", "unqualified",
                    f"{name} is assigned {code} on {s['date']} but isn’t qualified for it",
                    name, s["date"], s["shift_type"]))
            # no-nights rule
            if s["shift_type"] == "night" and meta is not None and not meta.get("works_nights", True):
                issues.append(_issue(
                    "error", "no_nights",
                    f"{name} is on a night shift on {s['date']} but is marked no-nights",
                    name, s["date"], "night"))
            # member preference: a day they asked off
            no_days = set((prefs.get(name) or {}).get("no_weekdays") or [])
            if no_days:
                try:
                    wd = dt.date.fromisoformat(s["date"]).weekday()
                    if wd in no_days:
                        issues.append(_issue(
                            "info", "pref_conflict",
                            f"{name} is scheduled on {s['date']}, a weekday they asked to avoid",
                            name, s["date"], s["shift_type"]))
                except (ValueError, KeyError, TypeError):
                    pass

        issues.extend(_fatigue_issues(name, worked))

    # understaffed days
    dates = set()
    for p in schedule.get("people", []):
        for s in p.get("shifts", []):
            if s.get("date"):
                dates.add(s["date"])
    for date in sorted(dates):
        for (loc, st), need in mins.items():
            have = coverage.get((date, loc, st), 0)
            if have < need:
                issues.append(_issue(
                    "warning", "understaffed",
                    f"{date}: {loc} {st} has {have} of {need} required",
                    None, date, st))
    return issues


def _fatigue_issues(name: str, worked: list[dict]) -> list[dict]:
    out: list[dict] = []
    # group worked shifts by date
    by_date: dict[str, list[dict]] = {}
    for s in worked:
        by_date.setdefault(s["date"], []).append(s)
    work_dates = sorted(by_date)

    # consecutive worked days
    run, prev = 0, None
    for d in work_dates:
        try:
            cur = dt.date.fromisoformat(d)
        except ValueError:
            continue
        run = run + 1 if (prev and (cur - prev).days == 1) else 1
        if run == MAX_CONSECUTIVE_DAYS + 1:
            out.append(_issue(
                "warning", "consecutive",
                f"{name} works {run}+ days in a row ending {d}", name, d))
        prev = cur

    # rest between consecutive shifts (esp. night -> day)
    timed = sorted((s for s in worked if _start_dt(s)), key=lambda s: _start_dt(s))
    for a, b in zip(timed, timed[1:]):
        end_a, start_b = _end_dt(a), _start_dt(b)
        if not end_a or not start_b:
            continue
        rest = (start_b - end_a).total_seconds() / 3600.0
        if 0 <= rest < MIN_REST_HOURS:
            out.append(_issue(
                "warning", "short_rest",
                f"{name} has only {rest:.0f}h rest before {b['date']} "
                f"({b['shift_type']}) after a {a['shift_type']} shift",
                name, b["date"], b["shift_type"]))

    # rolling 7-day hours
    if work_dates:
        hours_by_date = {d: sum(shift_hours(s) for s in ss) for d, ss in by_date.items()}
        ds = [dt.date.fromisoformat(d) for d in work_dates if _safe_date(d)]
        for anchor in ds:
            window = sum(h for d, h in hours_by_date.items()
                         if _safe_date(d) and 0 <= (anchor - dt.date.fromisoformat(d)).days < 7)
            if window > MAX_HOURS_PER_7:
                out.append(_issue(
                    "info", "weekly_hours",
                    f"{name} works {window:.0f}h in the 7 days ending {anchor.isoformat()}",
                    name, anchor.isoformat()))
                break
    return out


def _safe_date(d: str) -> bool:
    try:
        dt.date.fromisoformat(d)
        return True
    except (ValueError, TypeError):
        return False


def summarize(issues: list[dict]) -> dict:
    """Counts by severity, for a quick header."""
    out = {"error": 0, "warning": 0, "info": 0, "total": len(issues)}
    for i in issues:
        out[i["severity"]] = out.get(i["severity"], 0) + 1
    return out
