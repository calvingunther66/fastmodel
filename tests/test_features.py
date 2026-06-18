"""Tests for the store-backed feature additions: prefs, claims, swaps, templates,
exports, equity, and roster-aware coverage."""

import datetime as dt

from server.coverage import propose
from server.exports import person_csv, schedule_csv
from server.store import ScheduleStore


def _store(tmp_path):
    return ScheduleStore(tmp_path)


def _loc(date, code, st):
    from schedule_extractor.definitions import decode, shift_window
    s, e, c = shift_window(code, st)
    info = decode(code)
    return {"date": date, "code": code, "shift_type": st, "category": info["category"],
            "meaning": info["meaning"], "start": s, "end": e, "crosses_midnight": c,
            "available": True}


def _seed(store, people):
    store._write_json(store.schedule_path, {
        "parsed_sheet": "S", "date_range": {"start": "2026-08-01", "end": "2026-08-03"},
        "people": people, "warnings": []})


# ---- B4 preferences -------------------------------------------------------
def test_prefs_roundtrip(tmp_path):
    s = _store(tmp_path)
    saved = s.set_prefs("ALICE", {"no_weekdays": [5, 6, 9], "prefer_nights": True,
                                  "reminder_minutes": "120"})
    assert saved["no_weekdays"] == [5, 6]      # 9 dropped (out of range)
    assert saved["prefer_nights"] is True and saved["reminder_minutes"] == 120
    assert s.get_prefs("ALICE")["prefer_nights"] is True


# ---- B1 open-shift claims -------------------------------------------------
def test_claims(tmp_path):
    s = _store(tmp_path)
    s.add_claim("BOB", "ALICE", "2026-08-01", "day")
    s.add_claim("BOB", "ALICE", "2026-08-01", "day")  # idempotent
    assert s.claims_for("ALICE", "2026-08-01", "day") == ["BOB"]
    s.remove_claim("BOB", "ALICE", "2026-08-01", "day")
    assert s.claims_for("ALICE", "2026-08-01", "day") == []


def test_claims_coexist_with_callouts(tmp_path):
    s = _store(tmp_path)
    s.mark_sick("ALICE", "2026-08-01", "day", code="BC")
    s.add_claim("BOB", "ALICE", "2026-08-01", "day")
    assert len(s.list_callouts()) == 1 and s.claims_for("ALICE", "2026-08-01", "day") == ["BOB"]


# ---- B3 swaps -------------------------------------------------------------
def test_swap_applies_to_schedule(tmp_path):
    s = _store(tmp_path)
    _seed(s, [
        {"name": "ALICE", "shifts": [_loc("2026-08-01", "BC", "day")], "unavailable": [], "notes": []},
        {"name": "BOB", "shifts": [_loc("2026-08-02", "HC", "day")], "unavailable": [], "notes": []},
    ])
    sw = s.propose_swap("ALICE", "2026-08-01", "day", "BOB", "2026-08-02", "day")
    s.set_swap_status(sw["id"], "accepted")
    s.set_swap_status(sw["id"], "approved")
    sched = s.get_schedule()
    by = {p["name"]: p for p in sched["people"]}
    # ALICE now has BOB's HC day; BOB has ALICE's BC day
    assert any(x["code"] == "HC" and x.get("swapped_from") == "BOB" for x in by["ALICE"]["shifts"])
    assert any(x["code"] == "BC" and x.get("swapped_from") == "ALICE" for x in by["BOB"]["shifts"])


def test_swap_not_applied_until_approved(tmp_path):
    s = _store(tmp_path)
    _seed(s, [
        {"name": "ALICE", "shifts": [_loc("2026-08-01", "BC", "day")], "unavailable": [], "notes": []},
        {"name": "BOB", "shifts": [_loc("2026-08-02", "HC", "day")], "unavailable": [], "notes": []},
    ])
    sw = s.propose_swap("ALICE", "2026-08-01", "day", "BOB", "2026-08-02", "day")
    s.set_swap_status(sw["id"], "accepted")  # not yet approved
    by = {p["name"]: p for p in s.get_schedule()["people"]}
    assert all(x["code"] == "BC" for x in by["ALICE"]["shifts"])


# ---- C3 templates ---------------------------------------------------------
def test_templates(tmp_path):
    s = _store(tmp_path)
    s.save_template("BC weeks", {"0": {"day": "BC"}, "1": {"day": "BC"}})
    assert "BC weeks" in s.list_templates()
    s.delete_template("BC weeks")
    assert "BC weeks" not in s.list_templates()


# ---- D2 exports -----------------------------------------------------------
def test_exports(tmp_path):
    s = _store(tmp_path)
    _seed(s, [{"name": "ALICE", "shifts": [_loc("2026-08-01", "BC", "day")],
               "unavailable": [], "notes": []}])
    sched = s.get_schedule()
    csv_all = schedule_csv(sched)
    assert "ALICE" in csv_all and "BC" in csv_all and csv_all.startswith("person,")
    assert person_csv(sched, "ALICE") is not None
    assert person_csv(sched, "NOBODY") is None


# ---- D1 equity in leaderboard --------------------------------------------
def test_leaderboard_has_equity(tmp_path):
    s = _store(tmp_path)
    _seed(s, [{"name": "ALICE", "shifts": [
        _loc("2026-08-01", "BC", "night"),          # a night
        _loc("2026-08-02", "BC", "day"),            # 2026-08-02 is a Sunday => weekend
    ], "unavailable": [], "notes": []}])
    s._record_work(s.get_raw_schedule())
    row = next(r for r in s.leaderboard()["people"] if r["name"] == "ALICE")
    assert row["nights"] == 1 and row["weekends"] >= 1 and row["hours"] > 0


# ---- A1 roster-aware coverage --------------------------------------------
def test_coverage_roster_blocks_nights_and_uses_quals():
    sched = {"people": [
        {"name": "SICK", "shifts": [_loc("2026-08-01", "BC", "night")]},
        {"name": "NIGHTOK", "shifts": []},
        {"name": "DAYONLY", "shifts": []},
    ]}
    roster = {
        "NIGHTOK": {"clinics": {"BC"}, "works_nights": True},
        "DAYONLY": {"clinics": {"BC"}, "works_nights": False},
    }
    out = propose(sched, "SICK", "2026-08-01", "night", roster=roster)
    names = [c["name"] for c in out["free_candidates"]]
    assert "NIGHTOK" in names and "DAYONLY" not in names  # no-nights hard block
