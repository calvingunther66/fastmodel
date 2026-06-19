"""K3: fairness debt eases heavy-slot carriers off in the generator, and the
store computes debt from accumulated nights + current weekends/holidays."""

from server.generator import generate
from server.store import ScheduleStore


def test_debt_shifts_assignment_to_lower_debt_person():
    quals = {"HEAVY": {"clinics": {"BC"}, "works_nights": True, "employment": "career"},
             "LIGHT": {"clinics": {"BC"}, "works_nights": True, "employment": "career"}}
    # One BC day slot for one date; HEAVY carries debt so LIGHT should get it.
    out = generate("2026-07-01", "2026-07-01", quals,
                   requirements=[("BC", "day", 1)],
                   debt={"HEAVY": 10})
    assert "LIGHT" in out["assignments"]
    assert "HEAVY" not in out["assignments"]


def test_store_debt_counts_nights_and_weekends(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    # 2026-07-04 is a Saturday (weekend); a night shift there = 1 night + 1 weekend.
    s.create_schedule("T", "2026-07-04", "2026-07-04",
                      {"AMY": {"2026-07-04": {"night": "BC"}}})
    debt = s.fairness_debt()
    assert debt.get("AMY", 0) >= 2  # at least the night + the weekend
