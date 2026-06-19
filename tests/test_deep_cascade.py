"""I2: multi-step cascades for thin, qualification-constrained pools."""

from server.coverage import propose
from server.store import ScheduleStore


def _loc(date, code, st="day"):
    return {"date": date, "code": code, "shift_type": st, "category": "location",
            "meaning": code, "available": True}


def _schedule():
    # SICK needs BC night. Only M1 is qualified for BC (and is working HC day).
    # Backfilling HC needs M2 (working CV day). CV day is taken by free F.
    return {"people": [
        {"name": "SICK", "shifts": [_loc("2026-07-10", "BC", "night")]},
        {"name": "M1", "shifts": [_loc("2026-07-01", "BC"), _loc("2026-07-10", "HC")]},
        {"name": "M2", "shifts": [_loc("2026-07-01", "HC"), _loc("2026-07-10", "CV")]},
        {"name": "F", "shifts": [_loc("2026-07-01", "CV")]},  # free on the 10th
    ]}


def test_deep_cascade_found():
    out = propose(_schedule(), "SICK", "2026-07-10", "night")
    assert out["deep_cascades"], "expected a multi-step chain"
    chain = out["deep_cascades"][0]
    assert len(chain["steps"]) >= 2
    assert chain["backfill"] == "F"
    assert chain["steps"][0]["mover"] == "M1"


def test_apply_chain_executes(tmp_path):
    s = ScheduleStore(data_dir=tmp_path)
    # Build the same situation as a real stored schedule.
    s.create_schedule("T", "2026-07-01", "2026-07-10", {
        "SICK": {"2026-07-10": {"night": "BC"}},
        "M1": {"2026-07-01": {"day": "BC"}, "2026-07-10": {"day": "HC"}},
        "M2": {"2026-07-01": {"day": "HC"}, "2026-07-10": {"day": "CV"}},
        "F": {"2026-07-01": {"day": "CV"}},
    })
    out = propose(s.get_schedule(), "SICK", "2026-07-10", "night",
                  stats=s.aggregated_stats())
    chain = out["deep_cascades"][0]
    s.apply_chain("SICK", "2026-07-10", "night", chain["steps"], chain["backfill"])
    callouts = {(c["name"], c["shift_type"]): c for c in s.list_callouts()}
    # The open shift is now covered by M1, and the chain's links are recorded.
    assert callouts[("SICK", "night")]["covered_by"] == "M1"
    assert ("M1", "day") in callouts and ("M2", "day") in callouts
