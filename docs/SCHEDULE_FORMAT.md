# Schedule format & code reference

This is the **domain knowledge** behind the parser. Almost none of it is obvious
from the spreadsheet alone — it was supplied by the schedule owner. The parser
(`schedule_extractor/roster_extractor.py`) and the definitions
(`schedule_extractor/definitions.py`) implement exactly what's described here.

If the format ever changes, update **both** this document and `definitions.py`.

---

## 1. Workbook structure

- The workbook has **several tabs**: working drafts prefixed `KH-`, `NEW-`, `OLD-`,
  a `…(2)` copy, and the **canonical tab** named like `June 21 - July 18, 26`.
  **Use the canonical tab.** (The web Upload screen has a dropdown to pick it; the
  auto-picker chooses the sheet with the most people and can land on a draft.)
- The sheet is **extremely wide** (~16,000 mostly-empty "phantom" columns). Real
  data sits in roughly columns A–AD. This is why LibreOffice can fail to open it;
  the parser ignores the phantom width.
- The schedule covers ~4 weeks. The title encodes the start (`June 21`) and the
  two-digit year (`26` → 2026).

### Rows

| Row(s) | Meaning |
|--------|---------|
| Row 1  | Title (`June 21 - July 18, 26`) |
| Row 2  | **DATE** — day-of-month numbers across the columns (`21, 22, … 30, 1, 2, …`). The month **rolls over** when the number decreases (30 → 1 means July starts). |
| Row 3  | **DAY** — day-of-week letters (`S M T W Th F S …`). |
| Row 4 onward | **Person blocks**, 3 rows each (see below). |
| ~Rows 58–62 | **Footer / legend** (a code key, NOT people). Must be excluded. |

### Person blocks (the core idea)

Each person occupies a **3-row block** starting at row 4 (rows 4–6, 7–9, 10–12, …):

```
        | 21 | 22 | 23 | ...        <- dates (row 2/3)
BRADSHAW| BC |    |    |            offset 0  (name row)      = DAY shift
C: ...  |    |    |    |            offset 1  (contact row)   = MIDSHIFT (split)
P: ...  |    |    | BC |            offset 2  (contact row)   = NIGHT shift
```

- **Column A** of the block: the **name** (offset 0), then two contact lines
  (offset 1, 2) — e.g. `C: 818-…` (cell), `H: …` (home), `P: TXT TO CELL` (pager).
  Contact lines always contain a `:`; names never do (used to tell them apart).
- A code's **vertical level inside the box sets the shift level**:
  - **offset 0** (level with the name) → **day**
  - **offset 1** (middle) → **midshift** = the *second half of a split day*
    (e.g. Birth Center in the morning, Triage in the afternoon). **Rare.**
  - **offset 2** (bottom) → **night**
- The parser stops at the **last named block** (so the footer/legend below it is
  not parsed as people). There is also one **unnamed block** mid-sheet (row 16) that
  carries shift data but no name — it is emitted with `name: null` and a warning.

---

## 2. Shift codes

A **code** is a short token (1–3 letters, or `*`). Anything longer / free-text is
captured as a **note** instead. Codes fall into three categories.

### Locations (where the person is working)

| Code | Meaning | Clinic? |
|------|---------|---------|
| `BC`  | Birth Center | no |
| `HC`  | Hillcrest | no |
| `CV`  | Convoy | **yes** |
| `VLJ` | Villa La Jolla | **yes** |
| `RB`  | RB / Vía Tizón | **yes** |
| `MOS` | Medical Office South | **yes** |
| `ENC` | Encinitas | **yes** (also seen as a night code) |
| `NTAS`| (night code; full name unconfirmed) | — |
| `T`   | Triage | — (own hours) |

> **Rule of thumb:** *everything that isn't Birth Center or Hillcrest is a clinic.*
> Clinics = `{CV, VLJ, RB, MOS, ENC}`.

### Status / availability (not a worked location)

| Code | Meaning | Notes |
|------|---------|-------|
| `V` | Vacation | **Green cell = approved** (see colours). No fill = not yet approved. |
| `R` | Request (the person asked for that day) | |
| `H` | Holiday | Appeared on Jul 3 for nearly everyone (holiday weekend). |
| `A` | Available / on-call pool | Not a fixed assignment. |
| `OK`| **Alias for `A`** (Available / on-call pool) | |
| `BDay` | Birthday request (off) | Written at the bottom of the box as a request. Not in the sample tab, but appears in other tabs. |
| `no` | **Unavailable / out sick** | See availability rule below. |

### Undefined / ignored

`*` and `UL` appear once each and are intentionally **left undefined** (preserved
verbatim with `category: "unknown"`). Don't invent meanings for them.

---

## 3. Shift times

Times are local (Pacific). Only the windows below are asserted; everything else is
left blank (`start`/`end` = `null`). The **legend at the bottom of the sheet**
(rows ~59–62) is the source of truth and reads, e.g., `BC = LJ CNM Day 7:30a-8p`,
`LJ CNM Night 7:30p-8:00a`, `HC CNM Day 7:00a-7:30p`, `Triage 7:30a-6p`.

| Shift | Hours | Crosses midnight |
|-------|-------|------------------|
| **Any night** (offset 2) | `19:30` → `08:00` | yes |
| **Birth Center day** (`BC`, day) | `07:30` → `20:00` | no |
| **Hillcrest day** (`HC`, day) | `07:00` → `19:30` | no |
| **Triage** (`T`) | `07:30` → `18:00` | no |
| **Clinic full day** (CV/VLJ/RB/MOS/ENC) | `08:00` → `17:00` | no |
| **Clinic morning** (split, day row) | `08:00` → `12:00` | no |
| **Clinic afternoon** (split, mid row) | `13:00` → `17:00` | no |
| Status codes (`V`,`R`,`H`,`A`,`OK`,`no`) | — none — | — |

Morning clinic = **8–12**, afternoon clinic = **1–5**, full clinic day = **8–5**.

### Splits (clinic morning/afternoon)

A clinic day is a **full day unless the box's center bar is coloured in** — that's
the visual cue for a split. When split: the **day row** is the **morning** half and
the **middle row** is the **afternoon** half. Splits are rare ("almost never").

The parser flags a split when, for a date whose **day-row code is a worked
location**, either (a) both the day row and middle row carry a code, or (b) the
middle-row cell for that date has a solid fill (the coloured center bar). The
"worked location" guard is important: a **green vacation fill** spans all three
rows and must **not** be mistaken for a split bar.

---

## 4. Colours

- **Green-filled `V`** = **approved vacation**. Two greens are used in the file:
  bright `00B050` and light `CCFFCC`. The detector treats any fill whose green
  channel dominates (and is reasonably strong) as green → `approved: true`.
  A `V` with no fill → `approved: false`.
- A solid fill on a **middle-row** cell (for a worked location) is read as the
  **split center bar** (see above).

---

## 5. Availability ("no" = out sick) — the call-out workflow

When a cell contains **`no`** (or `no <code>`), the person is **not available /
out sick** for that date. This is the schedule owner's tool for handling call-outs:

- The date is added to that person's **`unavailable`** list.
- Any shift on that date is marked **`available: false`** — i.e. *this is the shift
  that needs covering.*
- `no` itself is never emitted as a shift code.

Example: CORTES has `no` on Jun 24 and Jul 17 (each above a `BC`), so those `BC`
shifts come out `available: false`.

---

## 6. Output JSON shape (roster layout)

`extract_roster(ws)` returns:

```json
{
  "sheet": "June 21 - July 18, 26",
  "parsed_sheet": "June 21 - July 18, 26",
  "available_sheets": ["KH-2…", "NEW-3…", "…", "June 21 - July 18, 26"],
  "date_range": { "start": "2026-06-21", "end": "2026-07-18" },
  "uploaded_at": "2026-06-17T…Z",
  "warnings": ["block at row 16 has no name in column A"],
  "people": [
    {
      "name": "HINER",
      "contact": ["C: 510-917-4707", "P: TXT TO CELL"],
      "shifts": [
        {
          "date": "2026-06-21",
          "code": "BC",
          "shift_type": "night",          // day | midshift | night
          "category": "location",         // location | status | unknown
          "meaning": "Birth Center",
          "start": "19:30",               // null when time is variable/none
          "end": "08:00",
          "crosses_midnight": true,
          "available": true               // false if a 'no' applies that date
          // "approved": true|false       // present only for V (vacation)
          // "split_day": true            // present only on split day/mid shifts
        }
      ],
      "unavailable": [
        { "date": "2026-06-24", "reason": "not available / out sick" }
      ],
      "notes": [
        { "date": null, "text": "Husband will be working … nights on 7/14" }
      ]
    }
  ]
}
```

Notes: free-text in a date cell is attached with its `date`; free-text in the
columns to the **right** of the calendar is attached with `date: null`.

---

## 7. Worked example (from the real June 21 – July 18 sheet)

- **BRADSHAW** — `BC` on the 21st, top of box → **day** Birth Center (07:30–20:00).
- **HINER** — `BC` at the **bottom** of the box on the 21st → **night** Birth
  Center (19:30 → 08:00 next day).
- **CHOI** — `H` (Holiday) on Jul 3 in the day row **and** `BC` in the night row →
  a holiday marker plus a night Birth Center shift the same date.
- **CORTES** — `no` above `BC` on Jun 24 & Jul 17 → out sick; those `BC` shifts are
  `available: false` (need coverage). Also a run of green `V` → approved vacation.
- This particular month only uses **`BC`** as an actual worked location; everyone
  else is on `H`/`R`/`V`/`A`. The clinic/HC/triage rules are encoded for months
  that use them.

---

## 8. Where this maps in code

| Concept | Code |
|---------|------|
| Block scan, 3 levels, splits, notes, availability | `roster_extractor.py` → `extract_roster()` |
| Date header + month rollover | `roster_extractor.py` → `_date_columns()`, `_build_date_axis()` |
| Footer/legend exclusion | `roster_extractor.py` (bounds scan to last named block) |
| `no` parsing | `roster_extractor.py` → `_parse_no()` |
| Code → meaning/category | `definitions.py` → `decode()`, `LOCATIONS`, `STATUS`, `CLINICS` |
| Shift time windows | `definitions.py` → `shift_window()` + `*_WINDOW` constants |
| Green vacation / center bar | `definitions.py` → `is_green_fill()`, `has_solid_fill()` |
| Offset → level | `definitions.py` → `OFFSET_LEVEL` |
