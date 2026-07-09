"""M1: every saved period is archived; re-upload keeps history; activate restores."""

from server.store import ScheduleStore


def test_periods_accumulate_and_activate(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    s.create_schedule("June", "2026-06-01", "2026-06-28",
                      {"AMY": {"2026-06-01": {"day": "BC"}}})
    s.create_schedule("July", "2026-07-01", "2026-07-28",
                      {"BEA": {"2026-07-01": {"night": "HC"}}})

    arch = s.list_archive()
    periods = [a["period"] for a in arch]
    assert "2026-06-01..2026-06-28" in periods
    assert "2026-07-01..2026-07-28" in periods
    # newest first; July is active (last saved)
    assert arch[0]["period"] == "2026-07-01..2026-07-28"
    assert arch[0]["active"] is True
    assert next(a for a in arch if a["period"].startswith("2026-06"))["active"] is False

    # the active schedule is July
    assert s.get_raw_schedule()["parsed_sheet"] == "July"
    # re-activate June -> it becomes active, July still archived
    s.activate_archived("2026-06-01..2026-06-28")
    assert s.get_raw_schedule()["parsed_sheet"] == "June"
    assert {a["period"] for a in s.list_archive()} == set(periods)


def test_get_archived_rejects_bad_period(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    assert s.get_archived("../etc/passwd") is None
    assert s.get_archived("not-a-period") is None
    assert s.activate_archived("../../x") is None
