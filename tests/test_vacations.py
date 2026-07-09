"""Vacation-approval workflow (H1): decisions override the workbook green fill,
flow into the schedule, and block the generator."""

from server.store import ScheduleStore
from server.generator import generate


def _store(tmp_path):
    return ScheduleStore(data_dir=tmp_path)


def test_pending_then_approve_then_deny(tmp_path):
    s = _store(tmp_path)
    # A created V shift has no workbook "approved" fill -> starts pending.
    s.create_schedule("T", "2026-07-01", "2026-07-03",
                      {"AMY": {"2026-07-02": {"day": "V"}}})
    vacs = s.list_vacations()
    assert len(vacs) == 1 and vacs[0]["status"] == "pending"

    s.set_vacation("AMY", "2026-07-02", "approved")
    assert s.list_vacations()[0]["status"] == "approved"
    assert s.approved_vacations() == {"AMY": {"2026-07-02"}}

    # The approval flows into the served schedule as approved=True.
    sched = s.get_schedule()
    vshift = sched["people"][0]["shifts"][0]
    assert vshift["approved"] is True and vshift["vacation_status"] == "approved"

    s.set_vacation("AMY", "2026-07-02", "denied")
    assert s.list_vacations()[0]["status"] == "denied"
    assert s.approved_vacations() == {}  # denied no longer blocks

    s.set_vacation("AMY", "2026-07-02", "pending")  # clear
    assert s.list_vacations()[0]["status"] == "pending"


def test_workbook_fill_is_default_until_overridden(tmp_path):
    s = _store(tmp_path)
    s.create_schedule("T", "2026-07-01", "2026-07-02",
                      {"BEA": {"2026-07-01": {"day": "V"}}})
    # Simulate a green-fill approval coming from the parser.
    raw = s.get_raw_schedule()
    raw["people"][0]["shifts"][0]["approved"] = True
    s._write_json(s.schedule_path, raw)

    v = s.list_vacations()[0]
    assert v["from_workbook"] is True and v["status"] == "approved"
    # An explicit deny overrides the green fill.
    s.set_vacation("BEA", "2026-07-01", "denied")
    assert s.list_vacations()[0]["status"] == "denied"


def test_generator_blocks_approved_vacation():
    quals = {"AMY": {"clinics": {"BC"}, "works_nights": True, "employment": "career"},
             "BEA": {"clinics": {"BC"}, "works_nights": True, "employment": "career"}}
    out = generate("2026-07-01", "2026-07-01", quals,
                   requirements=[("BC", "day", 1)],
                   unavailable={"AMY": {"2026-07-01"}})
    # AMY is blocked, so the only BC-day assignment must go to BEA.
    assert "AMY" not in out["assignments"]
    assert "BEA" in out["assignments"]


def test_set_vacation_rejects_bad_status(tmp_path):
    s = _store(tmp_path)
    import pytest
    with pytest.raises(ValueError):
        s.set_vacation("AMY", "2026-07-02", "maybe")
