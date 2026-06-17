"""Coverage suggestion engine (trial feature).

Given a shift that has been called out (someone marked sick), propose who could
work it. Two kinds of proposal:

* **free** — people available that day (on the Available/on-call pool, or simply
  not scheduled) who could just take the shift.
* **move** — people already working something else that day who are qualified for
  the open shift and could be reassigned (leaving their current task open).

This is a heuristic built on the data we have (no explicit per-person
qualifications exist in the workbook). "Qualified for a location" means the
person has worked that location at least once in the loaded schedule. Scores and
reasons are returned so the admin can see *why* each name was suggested.
"""

from __future__ import annotations

import copy

from schedule_extractor.definitions import decode, shift_window

# Status codes that mean a person is off / not available to cover that day.
_OFF_STATUS = {"V", "H", "R", "BDAY", "NO"}
# Status codes that mean a person is explicitly available to be assigned.
_AVAILABLE_STATUS = {"A", "OK"}


def _profiles(schedule: dict) -> dict:
    """Per-person capability profile: which locations they've worked, do nights?"""
    prof = {}
    for p in schedule.get("people", []):
        name = p.get("name")
        if not name:
            continue
        codes, nights = set(), False
        for s in p["shifts"]:
            if s.get("category") == "location":
                codes.add(s["code"].upper())
                if s.get("shift_type") == "night":
                    nights = True
        prof[name] = {"codes": codes, "nights": nights}
    return prof


def _entries_on(person: dict, date: str) -> list[dict]:
    return [s for s in person["shifts"] if s["date"] == date]


def _day_state(entries: list[dict]):
    """Classify a person's day: ('working', shift) | ('off', code) | ('free', None)."""
    working = [s for s in entries if s.get("category") == "location"]
    if working:
        return "working", working[0]
    for s in entries:
        if s.get("category") == "status" and s["code"].upper() in _OFF_STATUS:
            return "off", s["code"].upper()
    available = any(
        s.get("category") == "status" and s["code"].upper() in _AVAILABLE_STATUS
        for s in entries
    )
    return ("available" if available else "free"), None


def find_open_shift(schedule: dict, name: str, date: str, shift_type: str) -> dict | None:
    for p in schedule.get("people", []):
        if p.get("name") != name:
            continue
        for s in p["shifts"]:
            if s["date"] == date and s["shift_type"] == shift_type:
                return s
    return None


def propose(schedule: dict, name: str, date: str, shift_type: str) -> dict:
    """Return coverage proposals for the open shift (name, date, shift_type)."""
    open_shift = find_open_shift(schedule, name, date, shift_type)
    open_code = (open_shift or {}).get("code", "").upper()
    open_meaning = (open_shift or {}).get("meaning")
    is_night = shift_type == "night"

    profiles = _profiles(schedule)
    free, move = [], []

    for p in schedule.get("people", []):
        cand = p.get("name")
        if not cand or cand == name:
            continue
        prof = profiles.get(cand, {"codes": set(), "nights": False})
        qualified = open_code in prof["codes"] if open_code else False
        contact = p.get("contact", [])

        state, detail = _day_state(_entries_on(p, date))

        if state == "off":
            continue  # on vacation / holiday / requested off / sick — skip

        if state in ("available", "free"):
            reasons = []
            score = 0
            if state == "available":
                score += 50
                reasons.append("on the Available / on-call pool that day")
            else:
                score += 20
                reasons.append("nothing scheduled that day")
            if qualified:
                score += 25
                reasons.append(f"has worked {open_meaning or open_code} before")
            elif open_code:
                reasons.append(f"no record of working {open_meaning or open_code}")
            if is_night:
                if prof["nights"]:
                    score += 10
                    reasons.append("works night shifts")
                else:
                    score -= 5
                    reasons.append("no record of night shifts")
            free.append({
                "name": cand, "contact": contact, "status": state,
                "qualified": qualified, "score": score, "reasons": reasons,
            })

        elif state == "working":
            # Could be moved off their current assignment to cover the open shift.
            if not qualified:
                continue  # only suggest moving people qualified for the open shift
            cur = detail
            cur_label = f"{cur.get('meaning') or cur.get('code')} ({cur.get('shift_type')})"
            score = 25
            reasons = [
                f"qualified for {open_meaning or open_code}",
                f"currently on {cur_label}",
            ]
            # Available-pool / clinic assignments are easier to reassign.
            cur_code = cur.get("code", "").upper()
            if cur.get("shift_type") in ("day", "midshift") and cur_code not in ("BC", "HC"):
                score += 10
                reasons.append("current assignment looks reassignable")
            move.append({
                "name": cand, "contact": contact,
                "currently": cur_label, "score": score, "reasons": reasons,
            })

    free.sort(key=lambda c: (-c["score"], c["name"]))
    move.sort(key=lambda c: (-c["score"], c["name"]))

    return {
        "open_shift": {
            "name": name, "date": date, "shift_type": shift_type,
            "code": open_shift.get("code") if open_shift else None,
            "meaning": open_meaning,
            "start": open_shift.get("start") if open_shift else None,
            "end": open_shift.get("end") if open_shift else None,
        },
        "free_candidates": free[:8],
        "move_candidates": move[:8],
    }


def apply_overrides(schedule: dict, callouts: list[dict]) -> dict:
    """Return a copy of the schedule with call-outs flagged and covers injected.

    For each call-out: the named shift is marked unavailable; if it has been
    assigned a cover, a shift is added to the covering person (flowing into the
    grid and their .ics feed) tagged with whom they're covering for.
    """
    sched = copy.deepcopy(schedule)
    by_name = {p["name"]: p for p in sched.get("people", []) if p.get("name")}

    for co in callouts:
        person = by_name.get(co["name"])
        if not person:
            continue
        for s in person["shifts"]:
            if s["date"] == co["date"] and s["shift_type"] == co["shift_type"]:
                s["available"] = False
                s["called_out"] = co.get("reason", "called out")
                if not any(u["date"] == co["date"] for u in person.get("unavailable", [])):
                    person.setdefault("unavailable", []).append(
                        {"date": co["date"], "reason": co.get("reason", "called out")}
                    )
                break

        cover = co.get("covered_by")
        if cover and cover in by_name:
            code = co.get("code") or (find_open_shift(schedule, co["name"], co["date"], co["shift_type"]) or {}).get("code") or ""
            start, end, crosses = shift_window(code, co["shift_type"])
            info = decode(code) if code else {"category": None, "meaning": None}
            by_name[cover]["shifts"].append({
                "date": co["date"], "code": code, "shift_type": co["shift_type"],
                "category": info["category"], "meaning": info["meaning"],
                "start": start, "end": end, "crosses_midnight": crosses,
                "available": True, "covering_for": co["name"],
            })
            by_name[cover]["shifts"].sort(key=lambda s: (s["date"], s["shift_type"]))

    return sched
