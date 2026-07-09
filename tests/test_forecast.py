"""K2: the coverage forecaster flags gaps and single-points-of-failure."""

from server.forecast import forecast


def _loc(date, code, st="day"):
    return {"date": date, "code": code, "shift_type": st, "category": "location",
            "meaning": code, "available": True}


def _sched(people):
    return {"date_range": {"start": "2026-07-01", "end": "2026-07-01"}, "people": people}


REQS = [("BC", "day", 1), ("BC", "night", 1)]


def test_gap_when_understaffed():
    # Only a BC day is scheduled; BC night has nobody -> a gap.
    sched = _sched([{"name": "AMY", "shifts": [_loc("2026-07-01", "BC")]}])
    out = forecast(sched, requirements=REQS, today="2026-07-01")
    day = out["days"][0]
    assert day["risk"] == "gap"
    assert any(i["location"] == "BC" and i["level"] == "night" for i in day["issues"])
    assert out["summary"]["gap_days"] == 1


def test_thin_when_met_but_no_backup():
    # BC day + BC night both met by exactly one person, nobody free -> thin.
    sched = _sched([
        {"name": "AMY", "shifts": [_loc("2026-07-01", "BC", "day")]},
        {"name": "BEA", "shifts": [_loc("2026-07-01", "BC", "night")]},
    ])
    out = forecast(sched, requirements=REQS, today="2026-07-01")
    assert out["summary"]["gap_days"] == 0
    assert out["days"][0]["risk"] == "thin"


def test_ok_when_backup_available():
    # A third person, free and qualified for BC, removes the "thin" risk on day.
    sched = _sched([
        {"name": "AMY", "shifts": [_loc("2026-07-01", "BC", "day")]},
        {"name": "BEA", "shifts": [_loc("2026-07-01", "BC", "night")]},
        {"name": "CASS", "shifts": [_loc("2026-06-01", "BC")]},  # free on the 1st, qualified
    ])
    out = forecast(sched, requirements=REQS, today="2026-07-01")
    # day slot now has a backup; night still thin (CASS works day history only -> still
    # qualified for BC, free that day, but night needs works_nights unknown -> counts).
    risks = {i["level"]: i["severity"] for d in out["days"] for i in d["issues"]}
    assert risks.get("day") != "thin"  # day no longer flagged


def test_past_days_skipped():
    sched = _sched([{"name": "AMY", "shifts": [_loc("2026-07-01", "BC")]}])
    out = forecast(sched, requirements=REQS, today="2026-08-01")
    assert out["days"] == []
