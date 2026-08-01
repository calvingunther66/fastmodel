"""Extractor for the "blocked roster" layout (e.g. the June 21 - July 18 sheet).

Layout characteristics, established by inspecting the real file:

* Row 2 = day-of-month numbers (the DATE axis); row 3 = day-of-week letters.
  The month rolls over when the day number decreases (30 -> 1). The month and
  year come from the title, which is hand-written and often incomplete, so the
  resulting dates are checked against row 3 before being trusted.
* Each person occupies a **3-row block** starting at row 4: the name sits in
  column A on the block's top row; the two rows below hold contact info.
* Within a person's box, a code on the **top row (level with the name) is a DAY
  shift**; a code on a **lower row is a NIGHT shift** (the "smaller bottom box").
* Cells beyond the date columns (and any free-text inside a date column) are
  per-person **notes**, not shift codes.

Colour carries meaning here, but only *relative* colour. The sheet shades whole
weekend columns and draws each day box as one fill spanning two rows, so a fill
is only a mark on a particular shift when it differs from its column's baseline
and from the rest of its own box.

Codes are kept verbatim; their meaning/timing is supplied separately. The only
interpretation applied here is day-vs-night, which is purely positional.
"""

from __future__ import annotations

import datetime as dt
import re

from .definitions import (
    OFFSET_LEVEL,
    decode,
    fill_key,
    is_green_fill,
    is_known,
    shift_window,
)

# A shift code is a short alphabetic token (plus the "*" marker), e.g.
# BC, H, R, V, A, UL, OK, no, *. Anything else is treated as a note — except a
# longer token that is itself a defined code (NTAS, BDay), which the length cap
# would otherwise make unreachable.
_CODE_RE = re.compile(r"^[A-Za-z*]{1,3}$")

# "BC6" — a code with an orientation/shift counter typed onto the end. Only
# accepted when the letters are a defined code, so ordinary text can't match.
_COUNTED_CODE_RE = re.compile(r"^([A-Za-z]{1,4})\s*(\d{1,2})$")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Month *names*, matched anywhere in the title. Reading "the first three letters"
# instead turns a tab named "WorkingSept13 - Oct 10" into "Wor" and silently
# falls back to January.
_MONTH_NAME_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", re.IGNORECASE
)

# Row 3 spells the day of week: S M T W Th F S. "S" is Saturday or Sunday and
# "T" is Tuesday (Thursday is spelled "Th") — enough to check the axis against.
_DOW_LETTERS = {
    "M": {0}, "T": {1}, "W": {2}, "TH": {3}, "F": {4}, "S": {5, 6},
    "SA": {5}, "SU": {6},
}


def _is_code(text: str) -> bool:
    s = text.strip()
    return bool(_CODE_RE.match(s)) or is_known(s)


def _strip_counter(text: str):
    """Split 'BC6' into ('BC', '6') when the letters are a defined code.

    The workbook numbers a new hire's orientation shifts by typing the count next
    to the code. Returns (code, counter), or (None, None) for anything else.
    """
    m = _COUNTED_CODE_RE.match(text.strip())
    if m and is_known(m.group(1)):
        return m.group(1), m.group(2)
    return None, None


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
    """Pull the starting month/year out of a title like 'June 21 - July 18, 26'.

    Returns (month, year, found_month, found_year) so the caller can tell a real
    reading from a fallback and warn instead of shipping a wrong date axis.
    """
    text = (title or "").strip()
    m = _MONTH_NAME_RE.search(text)
    month = _MONTHS[m.group(1).lower()] if m else 1

    # The year trails the second date after a comma: "… - July 18, 26". A bare
    # trailing number is only a year when it is written in full — otherwise
    # "Sept 13 - Oct 10" would read the 10th of October as the year 2010.
    y = re.search(r",\s*'?(\d{2,4})\b", text) or re.search(r"(\d{4})\s*$", text)
    year, found_year = default_year, False
    if y:
        raw = int(y.group(1))
        candidate = raw + 2000 if raw < 100 else raw
        if 1900 <= candidate <= 2200:
            year, found_year = candidate, True
    return month, year, bool(m), found_year


def _period_title(ws) -> tuple[str, str]:
    """The sheet's period title, preferred over the tab name.

    Row 1 carries the real title ("September 13 - October 10, 26") even on tabs
    named things like "WorkingSept13 - Oct 10,  (4)", which have a word glued to
    the front and no year at all. Returns (title, where_it_came_from).
    """
    for cell in ws[1]:
        v = cell.value
        if isinstance(v, str) and _MONTH_NAME_RE.search(v) and re.search(r"\d", v):
            return v.strip(), "row 1"
    return (ws.title or ""), "sheet name"


def _weekday_match(date_axis, dow_row) -> tuple[int, int]:
    """(matches, comparable) between the built dates and the sheet's DAY row.

    Row 3 states the day of week for every column. It is the one independent
    check on the date axis: if the month or year is wrong, the weekdays stop
    lining up. Columns whose letter isn't recognised are skipped.
    """
    matches = comparable = 0
    for col, iso in date_axis.items():
        letter = dow_row.get(col)
        wanted = _DOW_LETTERS.get(str(letter).strip().upper()) if letter else None
        if not wanted:
            continue
        comparable += 1
        if dt.date.fromisoformat(iso).weekday() in wanted:
            matches += 1
    return matches, comparable


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


def _dow_row(ws, day_cols, header_row: int = 3) -> dict:
    """{column: day-of-week letter} from the sheet's DAY row."""
    wanted = {c for c, _ in day_cols}
    return {cell.column: cell.value for cell in ws[header_row]
            if cell.column in wanted and cell.value not in (None, "")}


def _dow_columns(ws, header_row: int = 3) -> list:
    """Every column whose DAY-row cell is a day-of-week letter.

    Row 2 is mostly formulas (`=B2+1`); a workbook re-saved by anything that
    doesn't evaluate them keeps the formulas but loses the cached numbers, and
    those columns then look like they aren't dates at all. Row 3 is plain text,
    so it still shows how wide the calendar really is.
    """
    return [cell.column for cell in ws[header_row]
            if str(cell.value).strip().upper() in _DOW_LETTERS]


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


def _try_date_axis(day_cols, month: int, year: int):
    """`_build_date_axis`, or None if that month/year can't hold these days.

    A misread month, or a Feb 29 checked against a non-leap year, would otherwise
    raise out of the middle of a parse and fail the whole upload.
    """
    try:
        return _build_date_axis(day_cols, month, year)
    except ValueError:
        return None


def _resolve_date_axis(ws, day_cols, default_year: int, warnings: list):
    """Build the date axis and check it against the sheet's own DAY row.

    The title is the only source for the month and year, and it is written by
    hand — so it gets verified, not trusted. A year the title never stated is
    filled in from the weekdays; a year it *did* state is left alone and any
    disagreement is reported. Either way nothing wrong is published silently: a
    schedule landing in the wrong month breaks every calendar feed at once.
    """
    title, source = _period_title(ws)
    month, year, found_month, found_year = _parse_start_month_year(title, default_year)
    if not found_month:
        warnings.append(
            f"could not read a month from the title {title!r} ({source}); "
            "assuming January — check the date range"
        )

    dow = _dow_row(ws, day_cols)
    candidates = sorted(range(year - 2, year + 3), key=lambda y: abs(y - year))
    axis = _try_date_axis(day_cols, month, year)
    if axis is not None:
        matches, comparable = _weekday_match(axis, dow)
        if not comparable or matches == comparable:
            return axis, title, month, year
    else:
        # The stated month/year can't hold these day numbers at all (a misread
        # month, or Feb 29 against a non-leap year).
        matches = comparable = 0
        warnings.append(
            f"{title!r} ({source}) gives {month}/{year}, which cannot hold the day "
            "numbers in the DATE row"
        )

    # The weekdays disagree. When the title never gave a year, the DAY row is the
    # better source; when it did, the owner's year stands and we only flag it.
    if not found_year or axis is None:
        for candidate in candidates:
            if candidate == year:
                continue
            alt = _try_date_axis(day_cols, month, candidate)
            if alt is None:
                continue
            alt_matches, alt_comparable = _weekday_match(alt, dow)
            if alt_comparable and alt_matches == alt_comparable:
                warnings.append(
                    f"title {title!r} ({source}) states no usable year; the DAY row "
                    f"matches {candidate}, using that instead of {year}"
                )
                return alt, title, month, candidate

    if axis is None:
        # Nothing lines up, but the caller still needs a usable axis: January can
        # hold any day number, so the dates stay parseable and the warnings above
        # say plainly that they are not to be trusted.
        return _build_date_axis(day_cols, 1, year), title, 1, year

    warnings.append(
        f"date axis disagrees with the DAY row ({matches}/{comparable} columns "
        f"match) — check the month and year in the title {title!r} ({source})"
    )
    return axis, title, month, year


def _column_baseline_fills(ws, date_cols, rows) -> dict:
    """The background fill of each date column, so real markup can be told apart.

    Whole weekend columns are shaded (pale green in the real workbooks) and that
    shading is *not* a mark on any one shift. Only **empty** cells are counted,
    since those show the background undisturbed, and the winner has to hold a
    strict majority of them — so one person's day box can never be mistaken for
    the whole column's styling.
    """
    baseline = {}
    rows = list(rows)
    for col in date_cols:
        counts: dict = {}
        total = 0
        for r in rows:
            cell = ws.cell(r, col)
            if cell.value not in (None, ""):
                continue
            total += 1
            key = fill_key(cell)
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            baseline[col] = None
            continue
        top = max(counts, key=counts.get)
        baseline[col] = top if counts[top] * 2 > total else None
    return baseline


def extract_roster(ws, *, default_year: int = 2026,
                   first_block_row: int = 4, block_size: int = 3):
    """Extract people, day/night shifts, and notes from a blocked-roster sheet."""
    warnings: list[str] = []
    day_cols = _date_columns(ws)
    if not day_cols:
        return {"sheet": ws.title, "people": [], "notes": [],
                "warnings": ["no date header (row 2) found"]}

    # The calendar is as wide as the DAY row. Fewer DATE columns than that means
    # dates were dropped, and days silently missing from a schedule is worse than
    # a schedule that refuses to look finished.
    dow_cols = _dow_columns(ws)
    if len(dow_cols) > len(day_cols):
        warnings.append(
            f"the DATE row has {len(day_cols)} day numbers but the DAY row spans "
            f"{len(dow_cols)} columns — {len(dow_cols) - len(day_cols)} dates were "
            "skipped. If the workbook was re-saved by a tool that doesn't evaluate "
            "formulas, open it in Excel and save again"
        )

    date_axis, title, start_month, year = _resolve_date_axis(
        ws, day_cols, default_year, warnings
    )
    last_date_col = max(c for c, _ in day_cols)
    date_col_set = {c for c, _ in day_cols}

    max_row = ws.max_row

    # Find the last real person block so the footer/legend (which sits in the
    # same column-A position but holds a code key, not names) isn't parsed as
    # people. A person name is non-empty and has no ':' (contact rows do).
    last_person_top = first_block_row
    r0 = first_block_row
    while r0 <= max_row:
        a = ws.cell(r0, 1).value
        if a not in (None, "") and ":" not in str(a):
            last_person_top = r0
        r0 += block_size
    scan_end = last_person_top + block_size - 1

    baseline_fills = _column_baseline_fills(
        ws, date_col_set, range(first_block_row, scan_end + 1)
    )

    people = []
    row = first_block_row
    while row <= scan_end:
        name = ws.cell(row, 1).value
        # A block exists wherever there is content on its top row; an empty
        # name still anchors a block (recorded as an unnamed entry).
        block_rows = list(range(row, min(row + block_size, scan_end + 1)))
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
                    counted, counter = _strip_counter(text)
                    if is_no:
                        unavailable_dates.add(date)
                        if affected and _is_code(affected):
                            records.append((date, offset, affected, cell))
                    elif _is_code(text):
                        records.append((date, offset, text, cell))
                    elif counted:
                        # "BC6" -> a real BC shift, plus the counter as a note
                        records.append((date, offset, counted, cell))
                        notes.append({"date": date, "text": text})
                    else:
                        notes.append({"date": date, "text": text})
                elif c > last_date_col:
                    # free-text note column to the right of the calendar
                    notes.append({"date": None, "text": text})

        # A date's day shift is "split" (morning vs afternoon) when its box has a
        # coloured center bar. The box itself is two rows tall and filled in one
        # colour, so a fill on the middle row only means something when it
        # *differs* from the day cell above it — otherwise every worked day in
        # the sheet reads as a split. The column baseline is subtracted first so
        # weekend shading, which covers both rows equally, never counts.
        # Splits only apply to a worked location on the day row.
        day_row = block_rows[0]
        mid_row = block_rows[1] if len(block_rows) > 1 else None
        offsets_by_date: dict[str, set[int]] = {}
        cols_by_date: dict[str, int] = {}
        day_code_by_date: dict[str, str] = {}
        for date, offset, code, cell in records:
            offsets_by_date.setdefault(date, set()).add(offset)
            cols_by_date[date] = cell.column
            if offset == 0:
                day_code_by_date[date] = code

        def _marked(row: int, col: int):
            """The cell's fill, or None when it just repeats the column's."""
            key = fill_key(ws.cell(row, col))
            return None if key == baseline_fills.get(col) else key

        split_dates = set()
        same_box_dates = set()
        for date, offs in offsets_by_date.items():
            col = cols_by_date[date]
            day_fill = _marked(day_row, col)
            mid_fill = _marked(mid_row, col) if mid_row is not None else None
            # One fill spanning both rows is a single tall box, not a center bar.
            same_box = day_fill is not None and mid_fill == day_fill
            if same_box:
                same_box_dates.add(date)
            day_code = day_code_by_date.get(date)
            if not day_code or decode(day_code)["category"] != "location":
                continue  # split only makes sense for a worked location
            center_bar = mid_fill is not None and mid_fill != day_fill
            if center_bar or (0 in offs and 1 in offs and not same_box):
                split_dates.add(date)

        shifts = []
        for date, offset, code, cell in records:
            # A code on the middle row of a single tall box is the second line of
            # that box's label ("APP" over "C", "NRP" over "HC"), not an
            # afternoon half. Keep it as a note so nothing is lost, but don't
            # invent a shift out of it.
            if offset == 1 and date in same_box_dates and date not in split_dates:
                notes.append({"date": date, "text": code})
                continue
            shift_type = OFFSET_LEVEL.get(offset, "night")
            info = decode(code)
            start, end, crosses = shift_window(
                code, shift_type, split=date in split_dates
            )
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
                # Green means approved only when it is green *for this cell*. The
                # real workbooks shade every Saturday and Sunday column pale
                # green, so a plain `is_green_fill` marks whichever days of a
                # vacation happen to fall on a weekend as approved and the rest
                # of the same block as not.
                shift["approved"] = (
                    fill_key(cell) != baseline_fills.get(cell.column)
                    and is_green_fill(cell)
                )
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
        "title": title,
        "date_range": {
            "start": date_axis[day_cols[0][0]],
            "end": date_axis[day_cols[-1][0]],
        },
        "people": people,
        "warnings": warnings,
    }
