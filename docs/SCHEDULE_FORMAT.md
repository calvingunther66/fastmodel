# Schedule format & code reference

This is the **domain knowledge** behind the parser. Almost none of it is obvious
from the spreadsheet alone — it was supplied by the schedule owner. The parser
(`schedule_extractor/roster_extractor.py`) and the definitions
(`schedule_extractor/definitions.py`) implement exactly what's described here.

If the format ever changes, update **both** this document and `definitions.py`.

---

## 1. Workbook structure

- The workbook has **several tabs**: working drafts prefixed `KH-`, `NEW-`, `OLD-`,
  `Working…`, a `…(2)` copy, and a tab named like `June 21 - July 18, 26`.
  The auto-picker chooses the sheet with the most people and shifts. **Don't assume
  the tab with the tidy name is the real one** — in the Sept 13 – Oct 10 workbook
  the tidy tab is an empty template and all the data lives on
  `WorkingSept13 - Oct 10,  (4)`. The Upload screen's dropdown overrides the pick.
- The sheet is **extremely wide** (~16,000 mostly-empty "phantom" columns). Real
  data sits in roughly columns A–AD. This is why LibreOffice can fail to open it;
  the parser ignores the phantom width.
- The schedule covers ~4 weeks. The title encodes the start (`June 21`) and the
  two-digit year (`26` → 2026).

### Where the title comes from

**Row 1 first, tab name second.** A tab name is not reliably the period title: it
carries prefixes (`WorkingSept13…`, `KH-2June 21…`) and often drops the year
entirely. Row 1 holds the real title on every tab, including the drafts.

This matters more than it sounds. Reading "the first three letters" of
`WorkingSept13 - Oct 10,  (4)` yields `Wor`, which is not a month, so the whole
schedule silently lands in **January** — every date, every calendar feed, off by
eight months, with nothing to indicate a problem. The month is now matched by
**name** anywhere in the title, and a title with no readable month warns.

A bare number at the end of a title is *not* a year: in `Sept 13 - Oct 10` the
trailing `10` is the day of the month. A year is only read after a comma
(`…, 26`) or written in full.

### Rows

| Row(s) | Meaning |
|--------|---------|
| Row 1  | Title (`June 21 - July 18, 26`) — the authoritative period title |
| Row 2  | **DATE** — day-of-month numbers across the columns (`21, 22, … 30, 1, 2, …`). The month **rolls over** when the number decreases (30 → 1 means July starts). Only the first cell of each month is a literal; the rest are formulas (`=B2+1`). |
| Row 3  | **DAY** — day-of-week letters (`S M T W Th F S …`), plain text. |
| Row 4 onward | **Person blocks**, 3 rows each (see below). |
| ~Rows 58–62 | **Footer / legend** (a code key, NOT people). Must be excluded. |

Row 3 is the **check on row 2**. The month and year are hand-written in the title,
so the built dates are compared against the day-of-week letters:

- they agree → the axis is trusted;
- they disagree and the title stated **no** year → a year within ±2 that does
  agree is used instead, with a warning;
- they disagree and the title **did** state a year → the owner's year stands and
  the disagreement is reported. The parser doesn't overrule what was written down.

Row 3 also tells the parser how wide the calendar is. Because row 2 is mostly
formulas, a workbook re-saved by anything that doesn't evaluate them (a script, a
converter) keeps the formulas but loses the cached numbers — those columns then
read as blank and their days vanish from the schedule. Fewer DATE columns than
DAY columns now raises a warning naming how many dates were skipped.

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
| `CNV` | Convoy — **this is how the workbooks spell it** | **yes** |
| `CV`  | Convoy — older short spelling, accepted as an alias of `CNV` | **yes** |
| `VLJ` | Villa La Jolla | **yes** |
| `RB`  | RB / Vía Tizón | **yes** |
| `MOS` | Medical Office South | **yes** |
| `ENC` | Encinitas | **yes** (also seen as a night code) |
| `NTAS`| (night code; full name unconfirmed) | — |
| `T`   | Triage — the legend calls it `LJ OBGYN APP A (Triage)` | — (own hours) |
| `APP` | `LJ OBGYN APP C (Triage/PP)` — a weekend shift, written as `APP` with a `C` on the line below | — (own hours) |

> **Rule of thumb:** *everything that isn't Birth Center or Hillcrest is a clinic.*
> Clinics = `{CNV, VLJ, RB, MOS, ENC}`.

**Spelling matters.** `CNV` is what the sheets contain; only `CV` was defined for a
long time, so every Convoy shift decoded as `unknown` — no meaning, no hours, no
colour, and invisible to the coverage and qualification engines. Both spellings now
decode, and `canonical_code()` folds `CV` onto `CNV` before any code is compared
across sources, so a roster written one way still matches a schedule written the
other. Pickers and the generator only ever offer the canonical spelling.

Codes are matched **case-insensitively** (`v` is `V`, `bday` is `BDay`) and may be
1–4 characters — the old 1–3 cap made `NTAS` and `BDay` unreachable even though both
were defined. A code with a counter typed onto it (`BC6`, a new hire's sixth
orientation shift) yields the shift plus a note holding the original text.

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

The Sept 13 – Oct 10 workbook also uses **`E`** (7×), **`MC`** (6×), **`NRP`** and
**`JD`** (1× each). These are unconfirmed, so they are left `unknown` rather than
guessed at — the validator flags each one so the owner can define it. `NRP` is
plausibly the Neonatal Resuscitation Program class and `JD` jury duty, but neither
has been confirmed, and a wrong meaning would put wrong hours in someone's calendar.

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

**Only *relative* colour means anything.** A person's day box is drawn as a single
fill spanning the day row *and* the middle row, so "the middle-row cell has a fill"
is true for essentially every worked day in the sheet — that test flagged **68 of 68**
worked days in the Sept 13 – Oct 10 workbook as splits, which for a clinic would
have halved the day to an 08:00–12:00 morning.

A split is flagged when, for a date whose **day-row code is a worked location**:

- **(a)** the middle-row cell is filled in a colour that **differs** from the day
  cell above it — a genuine centre bar drawn across one box; or
- **(b)** both rows carry a code *and* they are not one filled box.

Both tests are taken relative to the **column baseline** (see below), so column-wide
shading — which covers the day and middle rows equally — can never look like a bar.

#### The middle row is usually a second line, not a second shift

Every middle-row token in the real workbooks turned out to be the second line of the
day box's label, sharing the box's fill: `APP` over `C` (the shift is "APP C"), `NRP`
over `HC`, `BC` over `intern`, `CNV` over `1` (an orientation counter). None is an
afternoon half. When the middle-row cell is part of one filled box and no centre bar
is present, its token is recorded as a **note on that date** rather than invented as
a `midshift` — nothing is lost, and no phantom 13:00–17:00 shift appears in anyone's
calendar.

---

## 4. Colours

Colour in this workbook is **layered**, and only the top layer carries information:

| Layer | What it is | Meaning |
|-------|-----------|---------|
| Column shading | Every **Saturday and Sunday** column is filled `CCFFCC` (pale green) top to bottom, across all person rows | none — it's a weekend stripe |
| Box fill | A person's day box, one colour spanning the day + middle rows | which assignment, visually |
| A cell that differs from both | a deliberate mark | **this** is the signal |

### The column baseline

Each date column's **baseline** is the fill shared by most of its *empty* cells —
empty cells show the background undisturbed, and requiring a strict majority means
one person's box can never be mistaken for the whole column's styling. A fill only
means something when it differs from its column's baseline.

- **Green-filled `V`** = **approved vacation** — but only when that green is *not*
  the column's own shading. This is the trap: the weekend stripe is a pale green,
  so a naive green test marks whichever days of a vacation happen to fall on a
  Saturday or Sunday as approved and the rest of the very same block as not.
  WRIGHT's unbroken Sept 17–22 vacation came out as four days "not approved" and two
  days "approved"; COOPER's ten weekday vacation days, all "not approved".
- Fills may be **theme-based** rather than RGB (Excel's palette colours). Reading
  only `fgColor.rgb` makes those look like no fill at all — `fill_key()` handles
  rgb, theme, and indexed fills, and `is_green_fill()` reports theme fills as
  not-green rather than guessing a colour it cannot resolve.
- A fill on a **middle-row** cell is a **split center bar** only when it differs
  from the day cell's fill (see above).

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
  "title": "June 21 - July 18, 26",
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
columns to the **right** of the calendar is attached with `date: null`. `sheet` is
the tab name; `title` is the period title from row 1 — the UI shows `title`, since
the tab name can be a working name nobody recognises.

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
| Period title (row 1 over tab name) | `roster_extractor.py` → `_period_title()`, `_parse_start_month_year()` |
| DAY-row cross-check + year repair | `roster_extractor.py` → `_weekday_match()`, `_resolve_date_axis()` |
| Weekend shading vs. real marks | `roster_extractor.py` → `_column_baseline_fills()` |
| Footer/legend exclusion | `roster_extractor.py` (bounds scan to last named block) |
| `no` parsing | `roster_extractor.py` → `_parse_no()` |
| Code → meaning/category | `definitions.py` → `decode()`, `LOCATIONS`, `STATUS`, `CLINICS` |
| Alias folding (`CV` → `CNV`) | `definitions.py` → `canonical_code()`, `CODE_ALIASES` |
| Shift time windows | `definitions.py` → `shift_window()` + `*_WINDOW` constants |
| Green vacation / center bar | `definitions.py` → `is_green_fill()`, `has_solid_fill()`, `fill_key()` |
| Offset → level | `definitions.py` → `OFFSET_LEVEL` |
| Regression tests for all of the above | `tests/test_roster_layout.py` |
