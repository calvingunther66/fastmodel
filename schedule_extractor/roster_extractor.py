"""Extractor for the "blocked roster" layout (e.g. the June 21 - July 18 sheet).

Layout characteristics, established by inspecting the real file:

* Row 2 = day-of-month numbers (the DATE axis); row 3 = day-of-week letters.
  The month rolls over when the day number decreases (30 -> 1).
* Each person occupies a **3-row block** starting at row 4: the name sits in
  column A on the block's top row; the two rows below hold contact info.
* Within a person's box, a code on the **top row (level with the name) is a DAY
  shift**; a code on a **lower row is a NIGHT shift** (the "smaller bottom box").
* Cells beyond the date columns (and any free-text inside a date column) are
  per-person **notes**, not shift codes.

Codes are kept verbatim; their meaning/timing is supplied separately. The only
interpretation applied here is day-vs-night, which is purely positional.
"""

from __future__ import annotations

import datetime as dt
import re

from .definitions import (
    OFFSET_LEVEL,
    decode,
    is_green_fill,
    shift_window,
)

# A shift code is a short alphabetic token (plus the "*" marker), e.g.
# BC, H, R, V, A, UL, OK, no, *. Anything else is treated as a note.
_CODE_RE = re.compile(r"^[A-Za-z*]{1,3}$")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _is_code(text: str) -> bool:
    return bool(_CODE_RE.match(text.strip()))


def _parse_no(text: str):
    """Detect an availability flag.

    A cell of 'no' (optionally 'no <code>', e.g. 'no BC') means the person is
    NOT available / out sick for that day. Returns (is_unavailable, affected_code)
    where affected_code is the shift they can't cover, if named inline.
    """
    s = text.strip().lower()
    if s == "no":
        return True, None
    if s.startswith("no ") or s.startswith("no "):
        remainder = text.strip()[3:].strip()
        return True, (remainder if remainder else None)
    return False, None


def _parse_start_month_year(title: str, default_year: int):
    """Pull the starting month/year out of a title like 'June 21 - July 18, 26'."""
    month = 1
    m = re.search(r"([A-Za-z]{3})", title or "")
    if m:
        month = _MONTHS.get(m.group(1).lower(), 1)
    y = re.search(r"(\d{2,4})\s*$", (title or "").strip())
    year = default_year
    if y:
        raw = int(y.group(1))
        year = raw + 2000 if raw < 100 else raw
    return month, year


def _date_columns(ws, header_row: int = 2):
    """Columns whose header (row 2) is a day-of-month number, in order."""
    cols = []
    for cell in ws[header_row]:
        v = cell.value
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if float(v).is_integer() and 1 <= int(v) <= 31:
                cols.append((cell.column, int(v)))
        elif isinstance(v, str) and v.strip().isdigit() and 1 <= int(v.strip()) <= 31:
            cols.append((cell.column, int(v.strip())))
    return cols


def _build_date_axis(day_cols, start_month: int, start_year: int):
    """Turn ordered day numbers into ISO dates, rolling the month when days drop."""
    axis = {}
    month, year = start_month, start_year
    prev = None
    for col, day in day_cols:
        if prev is not None and day < prev:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        axis[col] = dt.date(year, month, day).isoformat()
        prev = day
    return axis


def extract_roster(ws, *, default_year: int = 2026,
                   first_block_row: int = 4, block_size: int = 3):
    """Extract people, day/night shifts, and notes from a blocked-roster sheet."""
    warnings: list[str] = []
    day_cols = _date_columns(ws)
    if not day_cols:
        return {"sheet": ws.title, "people": [], "notes": [],
                "warnings": ["no date header (row 2) found"]}

    start_month, year = _parse_start_month_year(ws.title, default_year)
    date_axis = _build_date_axis(day_cols, start_month, year)
    last_date_col = max(c for c, _ in day_cols)
    date_col_set = {c for c, _ in day_cols}

    people = []
    row = first_block_row
    max_row = ws.max_row
    while row <= max_row:
        name = ws.cell(row, 1).value
        # A block exists wherever there is content on its top row; an empty
        # name still anchors a block (recorded as an unnamed entry).
        block_rows = list(range(row, min(row + block_size, max_row + 1)))
        contact = [
            str(ws.cell(r, 1).value).strip()
            for r in block_rows[1:]
            if ws.cell(r, 1).value not in (None, "")
        ]

        # Collect raw records per date column, tracking 'no' availability and
        # keeping the cell (for fill colour -> approved vacation).
        records = []  # (date, offset, code, cell)
        unavailable_dates: set[str] = set()
        notes = []
        for offset, r in enumerate(block_rows):
            for cell in ws[r]:
                c = cell.column
                v = cell.value
                if v in (None, ""):
                    continue
                text = str(v).strip()
                if not text:
                    continue
                if c in date_col_set:
                    date = date_axis[c]
                    is_no, affected = _parse_no(text)
                    if is_no:
                        unavailable_dates.add(date)
                        if affected and _is_code(affected):
                            records.append((date, offset, affected, cell))
                    elif _is_code(text):
                        records.append((date, offset, text, cell))
                    else:
                        notes.append({"date": date, "text": text})
                elif c > last_date_col:
                    # free-text note column to the right of the calendar
                    notes.append({"date": None, "text": text})

        # A date is "split" when both the day row and the mid row are filled.
        offsets_by_date: dict[str, set[int]] = {}
        for date, offset, _code, _cell in records:
            offsets_by_date.setdefault(date, set()).add(offset)
        split_dates = {d for d, offs in offsets_by_date.items() if 0 in offs and 1 in offs}

        shifts = []
        for date, offset, code, cell in records:
            shift_type = OFFSET_LEVEL.get(offset, "night")
            info = decode(code)
            start, end, crosses = shift_window(code, shift_type)
            shift = {
                "date": date,
                "code": code,
                "shift_type": shift_type,
                "category": info["category"],
                "meaning": info["meaning"],
                "start": start,
                "end": end,
                "crosses_midnight": crosses,
                "available": date not in unavailable_dates,
            }
            if date in split_dates and offset in (0, 1):
                shift["split_day"] = True
            if code.strip().upper() == "V":
                shift["approved"] = is_green_fill(cell)
            shifts.append(shift)

        unavailable = [
            {"date": d, "reason": "not available / out sick"}
            for d in sorted(unavailable_dates)
        ]

        has_content = bool(name) or shifts or notes or unavailable
        if has_content:
            entry = {
                "name": (str(name).strip() if name not in (None, "") else None),
                "contact": contact,
                "shifts": sorted(
                    shifts, key=lambda s: (s["date"], s["shift_type"], s["code"])
                ),
                "unavailable": unavailable,
                "notes": notes,
            }
            if entry["name"] is None:
                warnings.append(f"block at row {row} has no name in column A")
            people.append(entry)

        row += block_size

    return {
        "sheet": ws.title,
        "date_range": {
            "start": date_axis[day_cols[0][0]],
            "end": date_axis[day_cols[-1][0]],
        },
        "people": people,
        "warnings": warnings,
    }
