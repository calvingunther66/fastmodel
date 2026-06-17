import threading
from pathlib import Path

from server.roster import StaffRoster
from server.store import ScheduleStore


def _store(tmp_path):
    s = ScheduleStore.__new__(ScheduleStore)
    s.data_dir = tmp_path
    for f, attr in {
        "current.xlsx": "xlsx_path", "schedule.json": "schedule_path",
        "tokens.json": "tokens_path", "overrides.json": "overrides_path",
        "contacts.json": "contacts_path", "availability.json": "offers_path",
        "stats.json": "stats_path", "settings.json": "settings_path",
    }.items():
        setattr(s, attr, tmp_path / f)
    s._lock = threading.Lock()
    return s


def test_create_schedule_decodes_codes_and_times(tmp_path):
    s = _store(tmp_path)
    res = s.create_schedule("Aug build", "2026-08-01", "2026-08-02", {
        "DOE, JANE": {"2026-08-01": {"day": "BC"}},
        "SMITH, ALEX": {"2026-08-01": {"night": "BC"}, "2026-08-02": {"day": "T"}},
    })
    assert res["created"] is True
    assert res["parsed_sheet"] == "Aug build"
    assert res["date_range"] == {"start": "2026-08-01", "end": "2026-08-02"}

    by = {p["name"]: p for p in res["people"]}
    doe = by["DOE, JANE"]["shifts"][0]
    assert doe["shift_type"] == "day" and doe["meaning"] == "Birth Center"
    assert (doe["start"], doe["end"]) == ("07:30", "20:00")

    alex = {(x["date"], x["shift_type"]): x for x in by["SMITH, ALEX"]["shifts"]}
    night = alex[("2026-08-01", "night")]
    assert (night["start"], night["end"], night["crosses_midnight"]) == ("19:30", "08:00", True)
    assert alex[("2026-08-02", "day")]["meaning"] == "Triage"

    # A created schedule becomes the active one and feeds the work stats.
    assert s.get_raw_schedule()["created"] is True
    assert s.aggregated_stats()["work"]["DOE, JANE"]["by_code"]["BC"] == 1


def test_roster_seeds_placeholder(tmp_path):
    r = StaffRoster(tmp_path)
    assert r.is_placeholder() is True
    names = [s["name"] for s in r.list()]
    assert names and all("clinics" in s for s in r.list())
    # replacing flips the placeholder flag and normalises fields
    r.replace([{"name": "REAL, PERSON", "clinics": ["bc"], "employment": "per_diem",
                "seniority": True, "works_nights": False}])
    assert r.is_placeholder() is False
    p = r.list()[0]
    assert p["clinics"] == ["BC"] and p["employment"] == "per_diem"
