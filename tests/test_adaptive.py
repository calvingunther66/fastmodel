import threading
from pathlib import Path

from server.audit import AuditLog
from server.coverage import propose
from server.store import ScheduleStore


def _store(tmp_path):
    s = ScheduleStore.__new__(ScheduleStore)
    s.data_dir = tmp_path
    s.xlsx_path = tmp_path / "current.xlsx"
    s.schedule_path = tmp_path / "schedule.json"
    s.tokens_path = tmp_path / "tokens.json"
    s.overrides_path = tmp_path / "overrides.json"
    s.contacts_path = tmp_path / "contacts.json"
    s.offers_path = tmp_path / "availability.json"
    s.stats_path = tmp_path / "stats.json"
    s._lock = threading.Lock()
    return s


def _loc(date, code, st):
    return {"date": date, "code": code, "shift_type": st, "category": "location",
            "meaning": code, "start": None, "end": None, "crosses_midnight": False,
            "available": True}


def _sched():
    return {
        "date_range": {"start": "2026-06-01", "end": "2026-06-02"},
        "parsed_sheet": "S",
        "people": [
            {"name": "SICK", "contact": [], "shifts": [_loc("2026-06-01", "BC", "night")],
             "unavailable": [], "notes": []},
            {"name": "ANNA", "contact": [], "shifts": [], "unavailable": [], "notes": []},
            {"name": "BECK", "contact": [], "shifts": [], "unavailable": [], "notes": []},
        ],
    }


def test_step_ups_raise_score(tmp_path):
    s = _store(tmp_path)
    base = propose(_sched(), "SICK", "2026-06-01", "night", stats=s.aggregated_stats())
    before = {c["name"]: c["score"] for c in base["free_candidates"]}
    assert before["ANNA"] == before["BECK"]  # identical to start

    for _ in range(2):
        s._bump_cover("ANNA", "BC", "night")
    learned = propose(_sched(), "SICK", "2026-06-01", "night", stats=s.aggregated_stats())
    after = {c["name"]: c for c in learned["free_candidates"]}
    assert after["ANNA"]["score"] > before["ANNA"]          # reliability lifted ANNA
    assert any("stepped up" in r for r in after["ANNA"]["reasons"])
    assert after["ANNA"]["score"] > after["BECK"]["score"]


def test_work_frequency_recorded_once_per_period(tmp_path):
    s = _store(tmp_path)
    s._record_work(_sched())
    s._record_work(_sched())  # same period -> replace, not double-count
    agg = s.aggregated_stats()
    assert agg["periods"] == 1
    assert agg["work"]["SICK"]["by_code"]["BC"] == 1


def test_audit_log_roundtrip(tmp_path):
    a = AuditLog(tmp_path)
    a.log("boss", "login")
    a.log("boss", "upload_schedule", {"sheet": "June"})
    rows = a.tail(10)
    assert rows[0]["action"] == "upload_schedule"   # newest first
    assert rows[0]["details"]["sheet"] == "June"
    assert rows[1]["action"] == "login"
