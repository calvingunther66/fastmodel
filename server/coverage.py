"""Coverage suggestion engine (trial feature).

Given a shift that has been called out (someone marked sick), propose who could
work it. Three kinds of proposal:

* **free** — people available that day (on the Available/on-call pool, or simply
  not scheduled) who could just take the shift.
* **move** — people already working something else that day who are qualified for
  the open shift and could be reassigned (leaving their current task open).
* **cascade** — a two-step chain: move a qualified person onto the open shift,
  then backfill *their* now-empty slot with a free person. Useful when nobody
  free is qualified for the open shift but someone working it is, and a free
  person can take the easier vacated slot.

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
    """Classify a person's day: working|off|available|free, plus the working shift."""
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


def _free_candidates(schedule, date, code, shift_type, exclude, profiles, offered=frozenset()):
    """Ranked people who are free/available to take a (date, code, shift_type) shift."""
    open_code = (code or "").upper()
    meaning = decode(code)["meaning"] if code else None
    is_night = shift_type == "night"
    out = []
    for p in schedule.get("people", []):
        cand = p.get("name")
        if not cand or cand in exclude:
            continue
        prof = profiles.get(cand, {"codes": set(), "nights": False})
        state, _ = _day_state(_entries_on(p, date))
        if state not in ("available", "free"):
            continue
        qualified = open_code in prof["codes"] if open_code else False
        reasons, score = [], 0
        if cand in offered:
            score += 30
            reasons.append("offered to cover this day")
        if state == "available":
            score += 50
            reasons.append("on the Available / on-call pool that day")
        else:
            score += 20
            reasons.append("nothing scheduled that day")
        if qualified:
            score += 25
            reasons.append(f"has worked {meaning or open_code} before")
        elif open_code:
            reasons.append(f"no record of working {meaning or open_code}")
        if is_night:
            if prof["nights"]:
                score += 10
                reasons.append("works night shifts")
            else:
                score -= 5
                reasons.append("no record of night shifts")
        out.append({
            "name": cand, "contact": p.get("contact", []),
            "status": state, "qualified": qualified, "score": score, "reasons": reasons,
        })
    out.sort(key=lambda c: (-c["score"], c["name"]))
    return out


def _move_candidates(schedule, date, code, shift_type, exclude, profiles):
    """Ranked people working a reassignable shift who are qualified for the open one."""
    open_code = (code or "").upper()
    meaning = decode(code)["meaning"] if code else None
    out = []
    for p in schedule.get("people", []):
        cand = p.get("name")
        if not cand or cand in exclude:
            continue
        prof = profiles.get(cand, {"codes": set(), "nights": False})
        state, detail = _day_state(_entries_on(p, date))
        if state != "working":
            continue
        if open_code not in prof["codes"]:
            continue  # only move people qualified for the open shift
        cur_code = detail.get("code", "").upper()
        cur_type = detail.get("shift_type")
        cur_meaning = detail.get("meaning") or detail.get("code")
        score = 25
        reasons = [f"qualified for {meaning or open_code}",
                   f"currently on {cur_meaning} ({cur_type})"]
        if cur_type in ("day", "midshift") and cur_code not in ("BC", "HC"):
            score += 10
            reasons.append("current assignment looks reassignable")
        out.append({
            "name": cand, "contact": p.get("contact", []),
            "currently": f"{cur_meaning} ({cur_type})",
            "from": {"code": detail.get("code"), "shift_type": cur_type, "meaning": cur_meaning},
            "score": score, "reasons": reasons,
        })
    out.sort(key=lambda c: (-c["score"], c["name"]))
    return out


def _cascades(schedule, sick_name, date, open_code, open_type, moves, profiles):
    """For each move candidate, find a free backfill for their vacated slot."""
    open_meaning = decode(open_code)["meaning"] if open_code else open_code
    cascades = []
    for m in moves:
        frm = m["from"]
        backfills = _free_candidates(
            schedule, date, frm["code"], frm["shift_type"],
            exclude={sick_name, m["name"]}, profiles=profiles,
        )
        if not backfills:
            continue
        best = backfills[0]
        cascades.append({
            "mover": m["name"],
            "from": frm,
            "open": {"code": open_code, "shift_type": open_type, "meaning": open_meaning},
            "backfill": best["name"],
            "backfill_contact": best["contact"],
            "backfill_reasons": best["reasons"],
            "summary": (
                f"Move {m['name']} from {frm['meaning']} ({frm['shift_type']}) "
                f"to cover {open_meaning} ({open_type}); "
                f"backfill {frm['meaning']} ({frm['shift_type']}) with {best['name']}."
            ),
            "score": m["score"] + best["score"],
        })
    cascades.sort(key=lambda c: (-c["score"], c["mover"]))
    return cascades


def propose(schedule: dict, name: str, date: str, shift_type: str,
            offered=frozenset()) -> dict:
    """Return coverage proposals for the open shift (name, date, shift_type).

    `offered` is the set of people who have declared they can cover that date.
    """
    open_shift = find_open_shift(schedule, name, date, shift_type)
    open_code = (open_shift or {}).get("code", "") or ""
    open_meaning = (open_shift or {}).get("meaning")

    profiles = _profiles(schedule)
    exclude = {name}
    free = _free_candidates(schedule, date, open_code, shift_type, exclude, profiles, offered)
    moves = _move_candidates(schedule, date, open_code, shift_type, exclude, profiles)
    cascades = _cascades(schedule, name, date, open_code.upper(), shift_type, moves, profiles)

    return {
        "open_shift": {
            "name": name, "date": date, "shift_type": shift_type,
            "code": open_shift.get("code") if open_shift else None,
            "meaning": open_meaning,
            "start": open_shift.get("start") if open_shift else None,
            "end": open_shift.get("end") if open_shift else None,
        },
        "free_candidates": free[:8],
        "move_candidates": moves[:8],
        "cascades": cascades[:5],
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
