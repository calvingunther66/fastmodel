"""Schedule diffing (M2).

Compare two parsed schedules (same shape as everywhere else) and report what
changed per person: shifts added, removed, or re-coded in the same slot. A "slot"
is (date, shift_type); a code change in a slot is a change, a slot appearing only
on one side is an add/remove. Used to show what a re-upload changed, and to
compare any two archived periods.
"""

from __future__ import annotations


def _slots(person: dict) -> dict:
    """{(date, shift_type): code} for a person's shifts."""
    out = {}
    for s in person.get("shifts", []):
        if s.get("date") and s.get("shift_type"):
            out[(s["date"], s["shift_type"])] = (s.get("code") or "").upper()
    return out


def diff_schedules(old: dict, new: dict) -> dict:
    """Return {people: {name: {added, removed, changed}}, summary}."""
    old_people = {p["name"]: p for p in (old or {}).get("people", []) if p.get("name")}
    new_people = {p["name"]: p for p in (new or {}).get("people", []) if p.get("name")}
    names = sorted(set(old_people) | set(new_people))

    people = {}
    n_add = n_rem = n_chg = 0
    for name in names:
        o = _slots(old_people.get(name, {}))
        n = _slots(new_people.get(name, {}))
        added, removed, changed = [], [], []
        for slot in sorted(set(o) | set(n)):
            date, stype = slot
            if slot in n and slot not in o:
                added.append({"date": date, "shift_type": stype, "code": n[slot]})
            elif slot in o and slot not in n:
                removed.append({"date": date, "shift_type": stype, "code": o[slot]})
            elif o[slot] != n[slot]:
                changed.append({"date": date, "shift_type": stype,
                                "from": o[slot], "to": n[slot]})
        if added or removed or changed:
            people[name] = {"added": added, "removed": removed, "changed": changed}
            n_add += len(added)
            n_rem += len(removed)
            n_chg += len(changed)

    return {"people": people,
            "summary": {"people_affected": len(people),
                        "added": n_add, "removed": n_rem, "changed": n_chg}}
