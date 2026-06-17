from server.coverage import apply_overrides, propose


def _loc(date, code, st, **kw):
    base = {"date": date, "code": code, "shift_type": st, "category": "location",
            "meaning": code, "start": None, "end": None, "crosses_midnight": False,
            "available": True}
    base.update(kw)
    return base


def _status(date, code, st="day"):
    return {"date": date, "code": code, "shift_type": st, "category": "status",
            "meaning": code, "start": None, "end": None, "crosses_midnight": False,
            "available": True}


D = "2026-06-21"


def _schedule():
    return {
        "people": [
            # The person who calls out — works a BC night that day.
            {"name": "SICK", "contact": [], "shifts": [_loc(D, "BC", "night")],
             "unavailable": [], "notes": []},
            # Explicitly available + has done BC nights -> strongest free candidate.
            {"name": "ANNA", "contact": ["C: 1"],
             "shifts": [_status(D, "A"), _loc("2026-06-10", "BC", "night")],
             "unavailable": [], "notes": []},
            # Free but never worked BC -> weaker.
            {"name": "BECK", "contact": [], "shifts": [], "unavailable": [], "notes": []},
            # Working a clinic day, but qualified for BC -> move candidate.
            {"name": "CARA", "contact": ["C: 3"],
             "shifts": [_loc(D, "CV", "day"), _loc("2026-06-12", "BC", "day")],
             "unavailable": [], "notes": []},
            # On vacation that day -> excluded.
            {"name": "DREW", "contact": [],
             "shifts": [_status(D, "V")], "unavailable": [], "notes": []},
        ]
    }


def test_propose_ranks_and_categorizes():
    prop = propose(_schedule(), "SICK", D, "night")
    assert prop["open_shift"]["code"] == "BC"

    free = [c["name"] for c in prop["free_candidates"]]
    assert free[0] == "ANNA"            # available + qualified + nights -> top
    assert "BECK" in free              # free but lower
    assert "DREW" not in free          # on vacation -> excluded
    assert "SICK" not in free          # never propose the called-out person

    move = [c["name"] for c in prop["move_candidates"]]
    assert move == ["CARA"]            # working, qualified for BC -> movable


def test_propose_offers_cascade():
    prop = propose(_schedule(), "SICK", D, "night")
    # CARA (working CV, qualified for BC) can move; a free person backfills CV.
    assert prop["cascades"], "expected at least one cascade"
    top = prop["cascades"][0]
    assert top["mover"] == "CARA"
    assert top["from"]["code"] == "CV"
    assert top["backfill"] in {"ANNA", "BECK"}
    assert "Move CARA" in top["summary"] and "backfill" in top["summary"].lower()


def test_cascade_overrides_chain():
    # Equivalent to applying the cascade: CARA covers SICK's BC night, ANNA
    # backfills CARA's CV day.
    callouts = [
        {"name": "SICK", "date": D, "shift_type": "night", "code": "BC",
         "reason": "out sick", "covered_by": "CARA"},
        {"name": "CARA", "date": D, "shift_type": "day", "code": "CV",
         "reason": "moved to cover SICK", "covered_by": "ANNA"},
    ]
    sched = apply_overrides(_schedule(), callouts)
    people = {p["name"]: p for p in sched["people"]}

    cara_bc = [s for s in people["CARA"]["shifts"] if s.get("covering_for") == "SICK"]
    assert cara_bc and cara_bc[0]["shift_type"] == "night"
    cara_cv = [s for s in people["CARA"]["shifts"] if s["code"] == "CV" and s["date"] == D][0]
    assert cara_cv["available"] is False              # CARA's old slot is now open
    anna_cv = [s for s in people["ANNA"]["shifts"] if s.get("covering_for") == "CARA"]
    assert anna_cv and anna_cv[0]["code"] == "CV"      # ANNA backfills it


def test_apply_overrides_flags_sick_and_injects_cover():
    callouts = [{"name": "SICK", "date": D, "shift_type": "night", "code": "BC",
                 "reason": "out sick", "covered_by": "ANNA"}]
    sched = apply_overrides(_schedule(), callouts)
    people = {p["name"]: p for p in sched["people"]}

    sick_shift = [s for s in people["SICK"]["shifts"] if s["date"] == D][0]
    assert sick_shift["available"] is False
    assert sick_shift["called_out"] == "out sick"
    assert any(u["date"] == D for u in people["SICK"]["unavailable"])

    cover = [s for s in people["ANNA"]["shifts"] if s.get("covering_for")]
    assert len(cover) == 1
    assert cover[0]["covering_for"] == "SICK"
    assert cover[0]["shift_type"] == "night"
    assert cover[0]["code"] == "BC"
    # night timing is filled from definitions
    assert (cover[0]["start"], cover[0]["end"]) == ("19:30", "08:00")
