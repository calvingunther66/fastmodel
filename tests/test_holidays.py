"""Holiday registry (H3): marked dates count as 'worked a holiday' in equity."""

from server.store import ScheduleStore


def test_holiday_registry_crud_and_equity(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    s.create_schedule("T", "2026-07-03", "2026-07-05", {
        "AMY": {"2026-07-04": {"day": "BC"}},   # works the holiday
        "BEA": {"2026-07-03": {"day": "BC"}},   # works a normal day
    })
    # No holidays yet -> nobody has worked one.
    lb = {r["name"]: r for r in s.leaderboard()["people"]}
    assert lb["AMY"]["holidays_worked"] == 0

    s.add_holiday("2026-07-04", "Independence Day")
    assert s.holiday_dates() == {"2026-07-04"}
    lb = {r["name"]: r for r in s.leaderboard()["people"]}
    assert lb["AMY"]["holidays_worked"] == 1
    assert lb["BEA"]["holidays_worked"] == 0

    s.remove_holiday("2026-07-04")
    assert s.list_holidays() == []


def test_add_holiday_validates_date(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    import pytest
    with pytest.raises(ValueError):
        s.add_holiday("not-a-date")
