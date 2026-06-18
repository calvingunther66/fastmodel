from server.validate import shift_hours, summarize, validate_schedule


def _loc(date, code, st, start=None, end=None, cross=False):
    return {"date": date, "code": code, "shift_type": st, "category": "location",
            "start": start, "end": end, "crosses_midnight": cross}


def test_shift_hours_night_crosses_midnight():
    assert shift_hours(_loc("2026-08-01", "BC", "night", "19:30", "08:00", True)) == 12.5
    assert shift_hours({"start": None, "end": None}) == 0.0


def test_no_roster_no_false_alarms():
    sched = {"people": [{"name": "A", "shifts": [
        _loc("2026-08-01", "BC", "day", "07:30", "20:00")]}]}
    assert validate_schedule(sched, roster=None) == []


def test_roster_flags_unqualified_and_no_nights():
    sched = {"people": [{"name": "A", "shifts": [
        _loc("2026-08-01", "BC", "night", "19:30", "08:00", True)]}]}
    roster = {"A": {"clinics": {"HC"}, "works_nights": False}}
    kinds = {i["kind"] for i in validate_schedule(sched, roster=roster)}
    assert "unqualified" in kinds and "no_nights" in kinds


def test_double_booking():
    sched = {"people": [{"name": "A", "shifts": [
        _loc("2026-08-01", "BC", "day"), _loc("2026-08-01", "HC", "day")]}]}
    assert any(i["kind"] == "double_booked" for i in validate_schedule(sched))


def test_unknown_code_but_star_ignored():
    sched = {"people": [{"name": "A", "shifts": [
        {"date": "2026-08-01", "code": "ZZ", "shift_type": "day", "category": "unknown"},
        {"date": "2026-08-02", "code": "*", "shift_type": "day", "category": "unknown"}]}]}
    kinds = [i for i in validate_schedule(sched) if i["kind"] == "unknown_code"]
    assert len(kinds) == 1 and kinds[0]["date"] == "2026-08-01"


def test_consecutive_days_flagged():
    shifts = [_loc(f"2026-08-0{d}", "CV", "day", "08:00", "17:00") for d in range(1, 9)]
    sched = {"people": [{"name": "A", "shifts": shifts}]}
    assert any(i["kind"] == "consecutive" for i in validate_schedule(sched))


def test_understaffed_off_by_default_on_by_request():
    sched = {"people": [{"name": "A", "shifts": [_loc("2026-08-01", "BC", "day")]}]}
    assert not any(i["kind"] == "understaffed" for i in validate_schedule(sched))
    on = validate_schedule(sched, minimums={("HC", "day"): 1})
    assert any(i["kind"] == "understaffed" for i in on)


def test_summarize():
    assert summarize([{"severity": "error"}, {"severity": "warning"}])["total"] == 2
