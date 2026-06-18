from server.generator import generate


def _quals(names, clinics, nights=True):
    return {n: {"clinics": set(clinics), "works_nights": nights,
                "employment": "career", "seniority": False} for n in names}


def test_generator_fills_core_slots_and_respects_quals():
    quals = _quals(["ALICE", "BOB", "CAROL", "DAN"], {"BC", "HC", "CV"})
    out = generate("2026-08-01", "2026-08-02", quals, prefs={}, stats={"work": {}})
    assert out["report"]["unfilled"] == []
    # every assigned location must be one the person is qualified for
    for person, days in out["assignments"].items():
        for date, levels in days.items():
            for level, code in levels.items():
                assert code in quals[person]["clinics"]


def test_generator_never_assigns_nights_to_no_nights_person():
    quals = _quals(["ALICE", "BOB"], {"BC", "HC"}, nights=True)
    quals["ALICE"]["works_nights"] = False
    out = generate("2026-08-01", "2026-08-05", quals, prefs={}, stats={"work": {}})
    nights = [(p, d) for p, days in out["assignments"].items()
              for d, levels in days.items() if "night" in levels]
    assert all(p != "ALICE" for p, _ in nights)


def test_generator_spreads_load_with_history():
    # BOB starts with heavy history; ALICE should be favoured for early slots.
    quals = _quals(["ALICE", "BOB"], {"BC", "HC"})
    stats = {"work": {"BOB": {"total": 50}}}
    out = generate("2026-08-01", "2026-08-01", quals, prefs={}, stats=stats)
    counts = {p: sum(len(lv) for lv in days.values()) for p, days in out["assignments"].items()}
    assert counts.get("ALICE", 0) >= counts.get("BOB", 0)


def test_generator_honours_no_weekday_pref():
    quals = _quals(["ALICE", "BOB"], {"BC", "HC"})
    # 2026-08-01 is a Saturday (weekday 5); ALICE avoids weekends.
    prefs = {"ALICE": {"no_weekdays": [5, 6]}}
    out = generate("2026-08-01", "2026-08-01", quals, prefs=prefs, stats={"work": {}})
    assert "ALICE" not in out["assignments"]
