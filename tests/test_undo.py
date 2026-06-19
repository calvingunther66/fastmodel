"""I1: undoing a cover reopens the shift and reverses the learned step-up."""

from server.store import ScheduleStore


def _store(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    s.create_schedule("T", "2026-07-01", "2026-07-02",
                      {"SICK": {"2026-07-01": {"day": "BC"}}})
    return s


def test_unassign_reopens_and_reverses_stat(tmp_path):
    s = _store(tmp_path)
    s.mark_sick("SICK", "2026-07-01", "day", code="BC")
    s.assign_cover("SICK", "2026-07-01", "day", "HELPER", code="BC")
    assert s.aggregated_stats()["covers"]["HELPER"]["count"] == 1
    co = s.list_callouts()[0]
    assert co["covered_by"] == "HELPER"

    assert s.unassign_cover("SICK", "2026-07-01", "day") is True
    co = s.list_callouts()[0]
    assert co["covered_by"] is None            # reopened, call-out kept
    assert s.aggregated_stats()["covers"]["HELPER"]["count"] == 0  # step-up reversed

    # Undoing again is a no-op (nothing assigned).
    assert s.unassign_cover("SICK", "2026-07-01", "day") is False


def test_clear_with_cover_also_reverses_stat(tmp_path):
    s = _store(tmp_path)
    s.assign_cover("SICK", "2026-07-01", "day", "HELPER", code="BC")
    assert s.aggregated_stats()["covers"]["HELPER"]["count"] == 1
    s.clear_callout("SICK", "2026-07-01", "day")
    assert s.list_callouts() == []
    assert s.aggregated_stats()["covers"]["HELPER"]["count"] == 0
