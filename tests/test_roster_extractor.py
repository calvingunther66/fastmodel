import openpyxl

from schedule_extractor.roster_extractor import extract_roster


def _roster_ws():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "June 30 - July 2, 26"  # drives start month June + year 2026
    # Date header (row 2) with a month rollover 30 -> 1.
    ws.cell(2, 1, "DATE")
    ws.cell(2, 2, 30)   # Jun 30
    ws.cell(2, 3, 1)    # Jul 1
    ws.cell(2, 4, 2)    # Jul 2
    ws.cell(3, 1, "DAY")
    # Person block: name on top row (day), codes below (night).
    ws.cell(4, 1, "SMITH")
    ws.cell(4, 2, "BC")            # day shift, Jun 30
    ws.cell(4, 5, "covers AM")     # note beyond the date columns
    ws.cell(5, 1, "C: 555-1212")
    ws.cell(5, 3, "R")             # night shift, Jul 1
    ws.cell(6, 1, "P: TXT")
    ws.cell(6, 4, "long free text note here")  # note inside a date col -> note
    return ws


def test_roster_dates_and_daynight():
    res = extract_roster(_roster_ws(), default_year=2026)
    assert res["date_range"] == {"start": "2026-06-30", "end": "2026-07-02"}
    assert len(res["people"]) == 1
    smith = res["people"][0]
    assert smith["name"] == "SMITH"
    assert smith["contact"] == ["C: 555-1212", "P: TXT"]

    shifts = {(s["date"], s["code"]): s["shift_type"] for s in smith["shifts"]}
    assert shifts[("2026-06-30", "BC")] == "day"     # top row = day
    assert shifts[("2026-07-01", "R")] == "night"    # lower row = night

    note_texts = {n["text"] for n in smith["notes"]}
    assert "covers AM" in note_texts                  # right of the calendar
    assert "long free text note here" in note_texts   # non-code in a date cell
