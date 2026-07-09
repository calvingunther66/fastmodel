"""M2: schedule diffing and re-upload diff capture."""

from server.diff import diff_schedules
from server.store import ScheduleStore


def _sched(people):
    return {"date_range": {"start": "2026-07-01", "end": "2026-07-02"}, "people": people}


def _loc(date, code, st="day"):
    return {"date": date, "code": code, "shift_type": st, "category": "location"}


def test_diff_added_removed_changed():
    old = _sched([{"name": "AMY", "shifts": [_loc("2026-07-01", "BC"), _loc("2026-07-02", "HC")]}])
    new = _sched([{"name": "AMY", "shifts": [_loc("2026-07-01", "CV"), _loc("2026-07-03", "BC")]}])
    d = diff_schedules(old, new)
    amy = d["people"]["AMY"]
    assert amy["changed"] == [{"date": "2026-07-01", "shift_type": "day", "from": "BC", "to": "CV"}]
    assert {s["date"] for s in amy["removed"]} == {"2026-07-02"}
    assert {s["date"] for s in amy["added"]} == {"2026-07-03"}
    assert d["summary"] == {"people_affected": 1, "added": 1, "removed": 1, "changed": 1}


def test_reupload_captures_diff(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    s.create_schedule("v1", "2026-07-01", "2026-07-02",
                      {"AMY": {"2026-07-01": {"day": "BC"}}})
    assert s.last_diff() is None  # first save of the period -> nothing to diff
    # re-create the same period with a change
    s.create_schedule("v2", "2026-07-01", "2026-07-02",
                      {"AMY": {"2026-07-01": {"day": "CV"}}})
    ld = s.last_diff()
    assert ld and ld["period"] == "2026-07-01..2026-07-02"
    assert ld["summary"]["changed"] == 1
    assert ld["people"]["AMY"]["changed"][0]["to"] == "CV"
