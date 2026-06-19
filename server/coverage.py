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

# Human reason for each off-status, shown so a coordinator sees *why* a qualified
# person is being skipped (rather than them silently vanishing from proposals).
_OFF_REASON = {
    "V": "on vacation", "H": "on holiday", "R": "requested off",
    "BDAY": "birthday off", "NO": "unavailable",
}


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


def _cover_average(schedule, stats) -> float:
    """Mean number of past cover step-ups across the team (named people)."""
    covers = (stats or {}).get("covers", {})
    names = [p["name"] for p in schedule.get("people", []) if p.get("name")]
    if not names:
        return 0.0
    return sum(covers.get(n, {}).get("count", 0) for n in names) / len(names)


def _adaptive_bonus(cand, open_code, shift_type, stats, cover_avg, reasons,
                    fairness_weight=0.5):
    """History-based adjustment on top of the static heuristics. Returns
    (bonus, fairness_phrase).

    Two signals, deliberately pulling in different directions, with their relative
    influence set by `fairness_weight` (0..1, default 0.5 = balanced):
      * competence — works this location/shift often → familiarity (weight 1-w).
      * fairness   — load-balances cover duty: people who've stepped up a lot get
                     eased off, people who rarely cover get a turn (weight w).
    At w=0 it's pure competence/availability; at w=1 it's pure load-balancing.
    """
    if not stats:
        return 0, ""
    comp_mult = (1.0 - fairness_weight) * 2.0   # 0..2 (1 at default)
    fair_mult = fairness_weight * 2.0           # 0..2 (1 at default)
    bonus = 0
    work = stats.get("work", {}).get(cand, {})
    covers = stats.get("covers", {}).get(cand, {})

    # --- competence (positive) ---
    worked_loc = work.get("by_code", {}).get(open_code, 0)
    if worked_loc:
        bonus += round(min(15, worked_loc * 2) * comp_mult)
        reasons.append(f"works {open_code} regularly ({worked_loc}× on record)")
    if shift_type == "night":
        nights = work.get("by_type", {}).get("night", 0)
        if nights:
            bonus += round(min(10, nights) * comp_mult)
            reasons.append(f"works nights regularly ({nights}× on record)")
    # learned affinity: people who have actually covered this location before are a
    # proven fit (the system gets smarter from real assignments — A4).
    covered_loc = covers.get("by_code", {}).get(open_code, 0)
    if covered_loc:
        bonus += round(min(8, covered_loc * 2) * comp_mult)
        reasons.append(f"has covered {open_code} before ({covered_loc}×)")

    # --- fairness / load balancing ---
    stepped = covers.get("count", 0)
    delta = cover_avg - stepped  # positive => below average => should get a turn
    fair = max(-30, min(30, round(delta * 6 * fair_mult)))
    bonus += fair
    if cover_avg <= 0:
        phrase = ""
    elif stepped == 0:
        phrase = "hasn’t been asked to cover yet — fair to give them a turn."
        reasons.append("hasn’t covered yet — balancing the load")
    elif delta > 0.5:
        phrase = f"has covered less than average ({stepped} vs {cover_avg:.1f}) — fair to ask."
        reasons.append(f"covers below team average ({stepped} vs {cover_avg:.1f})")
    elif delta < -0.5:
        phrase = f"has already stepped up a lot ({stepped}×) — easing their load."
        reasons.append(f"already covered {stepped}× — easing their load")
    else:
        phrase = ""
    return bonus, phrase



def _meta(roster, name):
    """Roster qualification metadata for a person, or None (use history)."""
    if not roster:
        return None
    return roster.get((name or "").upper())


def _qualified_for(open_code, prof, meta) -> bool:
    """True if the person is qualified for the open location.

    Prefers the real roster's clinic list when available; otherwise falls back to
    the history heuristic (has worked the location before)."""
    if not open_code:
        return False
    if meta is not None and meta.get("clinics"):
        return open_code in meta["clinics"]
    return open_code in prof["codes"]


def _free_candidates(schedule, date, code, shift_type, exclude, profiles,
                     offered=frozenset(), stats=None, cover_avg=0.0, fairness_weight=0.5,
                     roster=None):
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
        meta = _meta(roster, cand)
        # Hard rule: never put a no-nights person on a night shift (when we know).
        if is_night and meta is not None and not meta.get("works_nights", True):
            continue
        state, _ = _day_state(_entries_on(p, date))
        if state not in ("available", "free"):
            continue
        qualified = _qualified_for(open_code, prof, meta)
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
        roster_qual = meta is not None and meta.get("clinics")
        if qualified:
            score += 25
            reasons.append(f"qualified for {meaning or open_code}"
                           if roster_qual else f"has worked {meaning or open_code} before")
        elif open_code:
            reasons.append(f"not qualified for {meaning or open_code}"
                           if roster_qual else f"no record of working {meaning or open_code}")
        if is_night:
            night_ok = meta.get("works_nights", True) if meta is not None else prof["nights"]
            if night_ok:
                score += 10
                reasons.append("works night shifts")
            elif meta is None:
                score -= 5
                reasons.append("no record of night shifts")
        if meta is not None and meta.get("employment") == "per_diem":
            score += 5  # per-diem staff are the flex pool — lean on them first
            reasons.append("per-diem (flex pool)")
        bonus, fairness = _adaptive_bonus(cand, open_code, shift_type, stats,
                                          cover_avg, reasons, fairness_weight)
        score += bonus

        avail = ("on the on-call pool" if state == "available"
                 else ("offered to cover that day" if cand in offered else "free that day"))
        loc = meaning or open_code
        if roster_qual:
            comp = f"is qualified for {loc}" if qualified else f"is not qualified for {loc}"
        else:
            comp = f"has worked {loc} before" if qualified else f"hasn’t worked {loc} before"
        explanation = f"{cand} is {avail} and {comp}."
        if fairness:
            explanation += f" {cand} {fairness}"
        out.append({
            "name": cand, "contact": p.get("contact", []),
            "status": state, "qualified": qualified, "score": score,
            "explanation": explanation, "reasons": reasons,
        })
    out.sort(key=lambda c: (-c["score"], c["name"]))
    return out


def _move_candidates(schedule, date, code, shift_type, exclude, profiles,
                     stats=None, cover_avg=0.0, fairness_weight=0.5, roster=None):
    """Ranked people working a reassignable shift who are qualified for the open one."""
    open_code = (code or "").upper()
    meaning = decode(code)["meaning"] if code else None
    is_night = shift_type == "night"
    out = []
    for p in schedule.get("people", []):
        cand = p.get("name")
        if not cand or cand in exclude:
            continue
        prof = profiles.get(cand, {"codes": set(), "nights": False})
        meta = _meta(roster, cand)
        if is_night and meta is not None and not meta.get("works_nights", True):
            continue  # hard rule: no-nights person never moved onto a night
        state, detail = _day_state(_entries_on(p, date))
        if state != "working":
            continue
        if not _qualified_for(open_code, prof, meta):
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
        bonus, fairness = _adaptive_bonus(cand, open_code, shift_type, stats,
                                          cover_avg, reasons, fairness_weight)
        score += bonus
        explanation = (f"{cand} is qualified for {meaning or open_code} and currently on "
                       f"{cur_meaning} ({cur_type}), which can be reassigned.")
        if fairness:
            explanation += f" {cand} {fairness}"
        out.append({
            "name": cand, "contact": p.get("contact", []),
            "currently": f"{cur_meaning} ({cur_type})",
            "from": {"code": detail.get("code"), "shift_type": cur_type, "meaning": cur_meaning},
            "score": score, "explanation": explanation, "reasons": reasons,
        })
    out.sort(key=lambda c: (-c["score"], c["name"]))
    return out


def _unavailable_qualified(schedule, date, code, shift_type, exclude, profiles, roster):
    """Qualified people who are *off* that day (requested off / vacation / etc).

    Surfaced so the coordinator can see who they can't lean on and why — honouring
    R/V/H hints explicitly instead of silently dropping those people (H2)."""
    open_code = (code or "").upper()
    out = []
    for p in schedule.get("people", []):
        cand = p.get("name")
        if not cand or cand in exclude:
            continue
        state, detail = _day_state(_entries_on(p, date))
        if state != "off":
            continue
        prof = profiles.get(cand, {"codes": set(), "nights": False})
        meta = _meta(roster, cand)
        if not _qualified_for(open_code, prof, meta):
            continue  # only mention people who could otherwise have taken it
        reason = _OFF_REASON.get((detail or "").upper(), "off that day")
        out.append({"name": cand, "contact": p.get("contact", []),
                    "off_code": detail, "reason": reason})
    out.sort(key=lambda c: c["name"])
    return out


def _cascades(schedule, sick_name, date, open_code, open_type, moves, profiles,
              stats=None, cover_avg=0.0, fairness_weight=0.5, roster=None):
    """For each move candidate, find a free backfill for their vacated slot."""
    open_meaning = decode(open_code)["meaning"] if open_code else open_code
    cascades = []
    for m in moves:
        frm = m["from"]
        backfills = _free_candidates(
            schedule, date, frm["code"], frm["shift_type"],
            exclude={sick_name, m["name"]}, profiles=profiles, stats=stats,
            cover_avg=cover_avg, fairness_weight=fairness_weight, roster=roster,
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
            offered=frozenset(), stats=None, fairness_weight=0.5, roster=None) -> dict:
    """Return coverage proposals for the open shift (name, date, shift_type).

    `offered` is the set of people who have declared they can cover that date.
    `stats` (optional) is accumulated work/cover history that makes scoring adaptive.
    `fairness_weight` (0..1) dials competence vs load-balancing.
    `roster` (optional) is {NAME: {clinics, works_nights, employment, seniority}} from
    the real staff roster; when present it drives qualification and a hard no-nights
    rule, otherwise the engine falls back to the work-history heuristic.
    """
    open_shift = find_open_shift(schedule, name, date, shift_type)
    open_code = (open_shift or {}).get("code", "") or ""
    open_meaning = (open_shift or {}).get("meaning")

    profiles = _profiles(schedule)
    cover_avg = _cover_average(schedule, stats)
    exclude = {name}
    free = _free_candidates(schedule, date, open_code, shift_type, exclude, profiles,
                            offered, stats, cover_avg, fairness_weight, roster)
    moves = _move_candidates(schedule, date, open_code, shift_type, exclude, profiles,
                             stats, cover_avg, fairness_weight, roster)
    cascades = _cascades(schedule, name, date, open_code.upper(), shift_type, moves,
                         profiles, stats, cover_avg, fairness_weight, roster)
    unavailable = _unavailable_qualified(schedule, date, open_code, shift_type,
                                         exclude, profiles, roster)

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
        "unavailable_qualified": unavailable[:8],
    }


def _move_shift(by_name, frm, date, shift_type, to):
    """Move a worked shift from one person to another (for swaps)."""
    src, dst = by_name.get(frm), by_name.get(to)
    if not src or not dst:
        return
    for s in list(src["shifts"]):
        if (s["date"] == date and s["shift_type"] == shift_type
                and s.get("category") == "location"):
            src["shifts"].remove(s)
            moved = {**s, "swapped_from": frm}
            dst["shifts"].append(moved)
            dst["shifts"].sort(key=lambda x: (x["date"], x["shift_type"]))
            return


def apply_swaps(schedule: dict, swaps: list[dict]) -> dict:
    """Apply approved swaps in place: each party takes the other's shift."""
    by_name = {p["name"]: p for p in schedule.get("people", []) if p.get("name")}
    for sw in swaps or []:
        if sw.get("status") != "approved":
            continue
        _move_shift(by_name, sw["a_person"], sw["a_date"], sw["a_type"], sw["b_person"])
        _move_shift(by_name, sw["b_person"], sw["b_date"], sw["b_type"], sw["a_person"])
    return schedule


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
