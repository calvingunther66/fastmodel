"""H2: qualified people who are off that day surface in proposals with a reason."""

from server.coverage import propose


def _loc(date, code, st="day"):
    return {"date": date, "code": code, "shift_type": st, "category": "location",
            "meaning": code, "available": True}


def _status(date, code):
    return {"date": date, "code": code, "shift_type": "day", "category": "status",
            "meaning": code, "available": True}


def test_requested_off_qualified_person_is_surfaced():
    schedule = {"people": [
        {"name": "SICK", "shifts": [_loc("2026-07-02", "BC")]},
        # REQ has worked BC before (qualified by history) but requested off (R) that day.
        {"name": "REQ", "shifts": [_loc("2026-07-01", "BC"), _status("2026-07-02", "R")]},
    ]}
    out = propose(schedule, "SICK", "2026-07-02", "day")
    names = {u["name"]: u for u in out["unavailable_qualified"]}
    assert "REQ" in names
    assert names["REQ"]["reason"] == "requested off"
    # ...and they are NOT offered as a free candidate.
    assert "REQ" not in {c["name"] for c in out["free_candidates"]}


def test_off_but_unqualified_is_not_listed():
    schedule = {"people": [
        {"name": "SICK", "shifts": [_loc("2026-07-02", "BC")]},
        # Worked HC only -> not qualified for BC -> shouldn't be mentioned.
        {"name": "OTHER", "shifts": [_loc("2026-07-01", "HC"), _status("2026-07-02", "V")]},
    ]}
    out = propose(schedule, "SICK", "2026-07-02", "day")
    assert "OTHER" not in {u["name"] for u in out["unavailable_qualified"]}
