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
    s.settings_path = tmp_path / "settings.json"
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


def test_fairness_balances_load(tmp_path):
    s = _store(tmp_path)
    base = propose(_sched(), "SICK", "2026-06-01", "night", stats=s.aggregated_stats())
    before = {c["name"]: c["score"] for c in base["free_candidates"]}
    assert before["ANNA"] == before["BECK"]  # identical to start

    # ANNA keeps stepping up; the model should now favour BECK (share the load).
    for _ in range(3):
        s._bump_cover("ANNA", "BC", "night")
    learned = propose(_sched(), "SICK", "2026-06-01", "night", stats=s.aggregated_stats())
    after = {c["name"]: c for c in learned["free_candidates"]}
    assert after["BECK"]["score"] > after["ANNA"]["score"]      # fairness lifts the under-coverer
    assert after["ANNA"]["score"] < before["ANNA"]              # over-coverer eased off
    assert any("easing their load" in r for r in after["ANNA"]["reasons"])
    assert learned["free_candidates"][0]["name"] == "BECK"      # BECK now recommended first
    # every recommendation carries a plain-English explanation
    assert all(c.get("explanation") for c in learned["free_candidates"])


def test_work_frequency_recorded_once_per_period(tmp_path):
    s = _store(tmp_path)
    s._record_work(_sched())
    s._record_work(_sched())  # same period -> replace, not double-count
    agg = s.aggregated_stats()
    assert agg["periods"] == 1
    assert agg["work"]["SICK"]["by_code"]["BC"] == 1


def test_fairness_weight_controls_balance(tmp_path):
    s = _store(tmp_path)
    for _ in range(4):
        s._bump_cover("ANNA", "BC", "night")  # ANNA is a heavy coverer
    st = s.aggregated_stats()

    # Pure competence: ANNA (experienced/works it) is not penalised for covering.
    comp = propose(_sched(), "SICK", "2026-06-01", "night", stats=st, fairness_weight=0.0)
    comp_scores = {c["name"]: c["score"] for c in comp["free_candidates"]}
    # Pure fairness: ANNA is pushed below BECK to spread the load.
    fair = propose(_sched(), "SICK", "2026-06-01", "night", stats=st, fairness_weight=1.0)
    fair_scores = {c["name"]: c["score"] for c in fair["free_candidates"]}

    assert comp_scores["ANNA"] >= comp_scores["BECK"]   # competence doesn't punish ANNA
    assert fair_scores["BECK"] > fair_scores["ANNA"]    # fairness favours BECK


def test_fairness_weight_setting_clamped(tmp_path):
    s = _store(tmp_path)
    assert s.get_fairness_weight() == 0.5            # default
    assert s.set_fairness_weight(0.8) == 0.8
    assert s.get_fairness_weight() == 0.8            # persisted
    assert s.set_fairness_weight(5) == 1.0           # clamped high
    assert s.set_fairness_weight(-3) == 0.0          # clamped low


def test_leaderboard_ranks_by_covers(tmp_path):
    s = _store(tmp_path)
    s._record_work(_sched())
    for _ in range(3):
        s._bump_cover("ANNA", "BC", "night")
    s._bump_cover("BECK", "BC", "night")
    board = s.leaderboard()
    names = [r["name"] for r in board["people"]]
    assert names[0] == "ANNA" and names[1] == "BECK"   # ranked by covers desc
    top = board["people"][0]
    assert top["covers"] == 3 and top["covers_by_type"]["night"] == 3
    # everyone on the schedule appears, even with zero history
    assert "SICK" in names


def test_audit_log_roundtrip(tmp_path):
    a = AuditLog(tmp_path)
    a.log("boss", "login")
    a.log("boss", "upload_schedule", {"sheet": "June"})
    rows = a.tail(10)
    assert rows[0]["action"] == "upload_schedule"   # newest first
    assert rows[0]["details"]["sheet"] == "June"
    assert rows[1]["action"] == "login"
