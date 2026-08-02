from schedule_extractor.definitions import apply_triage_weekly_adjustment


def _location(date, code, start, end, crosses=False):
    return {"date": date, "code": code, "category": "location",
            "start": start, "end": end, "crosses_midnight": crosses}


def test_triage_adjustment_is_idempotent_with_two_triage_shifts_in_one_week():
    """Two Triage shifts in the same week must not oscillate on repeated runs.

    Regression test: the migration script (tools/fix_triage_hours.py) re-runs
    this against already-adjusted data. An earlier version summed each *other*
    triage shift's current (possibly already-shortened) duration, so shortening
    one shift lowered the week's total and flipped the other back to standard
    on the next run -- non-deterministic depending on run count.
    """
    shifts = [
        _location("2026-06-21", "CV", "08:00", "17:00"),  # 9h
        _location("2026-06-22", "CV", "08:00", "17:00"),  # 9h
        _location("2026-06-23", "CV", "08:00", "17:00"),  # 9h -> 27h other clinic work
        _location("2026-06-24", "T", "07:30", "18:00"),   # triage #1, same week
        _location("2026-06-25", "T", "07:30", "18:00"),   # triage #2, same week
    ]

    apply_triage_weekly_adjustment(shifts)
    by_date = {s["date"]: s for s in shifts}
    # 27h other + a standard 10h triage > 40h for either -> both shorten.
    assert (by_date["2026-06-24"]["start"], by_date["2026-06-24"]["end"]) == ("07:30", "16:00")
    assert (by_date["2026-06-25"]["start"], by_date["2026-06-25"]["end"]) == ("07:30", "16:00")

    snapshot = [dict(s) for s in shifts]
    apply_triage_weekly_adjustment(shifts)  # re-run, as the migration script does
    assert shifts == snapshot


def test_triage_adjustment_light_week_stays_standard():
    shifts = [
        _location("2026-06-21", "CV", "08:00", "17:00"),  # 9h, well under the threshold
        _location("2026-06-24", "T", "07:30", "18:00"),
    ]
    apply_triage_weekly_adjustment(shifts)
    assert (shifts[1]["start"], shifts[1]["end"]) == ("07:30", "18:00")
