# Schedule Extractor (prototype)

Takes an Excel workbook and extracts **someone's schedule** into structured JSON.

Schedules can live in a workbook two ways, and this tool handles both, per sheet,
automatically:

- **Cells** — shift codes typed into spreadsheet cells. Read directly and exactly.
- **Image** — a screenshot / scan / photo of a roster pasted into the sheet.
  Extracted and run through OCR (Tesseract).

The output is **raw**: for each person, the verbatim code found on each date. It does
**not** interpret what the codes mean — mapping codes (`D`, `N`, `OFF`, …) to shift
start/end times is a later step you'll supply.

## Install

```bash
bash setup.sh          # installs Tesseract (best-effort) + Python deps
# or just the Python deps:
pip install -r requirements.txt
```

Tesseract is only needed for image-based sheets. Without it, the cell path still works
and image sheets are saved to disk for inspection with a warning (OCR skipped).

## Usage

```bash
python -m schedule_extractor path/to/schedule.xlsx -o schedule.json --pretty
```

Options:

| Flag | Meaning |
|------|---------|
| `-o, --output` | Write JSON to a file (default: stdout) |
| `--header-row N` | Force the 1-based row holding the dates (default: auto-detect) |
| `--name-col X` | Force the name column, letter or 1-based number (default: auto-detect) |
| `--image-dir DIR` | Where to save extracted images (default: `extracted_images/`) |
| `--pretty` | Pretty-print the JSON |

## Try it

```bash
python tools/make_sample.py                                  # builds samples/sample_schedule.xlsx
python -m schedule_extractor samples/sample_schedule.xlsx -o out.json --pretty
python -m pytest                                             # run the tests
```

## Output schema

```json
{
  "source_file": "samples/sample_schedule.xlsx",
  "extracted_at": "2026-06-16T12:00:00Z",
  "sheets": [
    {
      "name": "June",
      "source_type": "cells",
      "date_axis": ["2026-06-01", "2026-06-02"],
      "people": [
        { "name": "John Doe",
          "shifts": [ {"date": "2026-06-01", "raw_code": "D"},
                      {"date": "2026-06-02", "raw_code": "OFF"} ] }
      ],
      "warnings": ["header row auto-detected at row 2", "name column = A"]
    }
  ],
  "images": [
    { "sheet": "Scanned", "file": "extracted_images/Scanned_1.png",
      "ocr_available": true, "ocr_text": "Name Mon Tue Wed\nAlice D N OFF" }
  ]
}
```

## How detection works

- **Header row**: the row with the most date-like cells (real dates, `Mon`/`Tue`/…, or
  numbers 1–31). Its date-like columns become the date axis.
- **Name column**: the left-most column before the dates that holds text labels on the
  data rows.
- Both are overridable via `--header-row` / `--name-col` for unusual layouts. The
  decisions taken are reported in each sheet's `warnings`.

## Blocked-roster layout (`--layout roster`)

Some real rosters encode the schedule by **box position** rather than by a flat
grid. Each person is a 3-row box (name on top, two contact rows below), the date
numbers live on row 2 (with month rollover), and a code's **vertical level**
inside the box sets the shift level:

- **top row** (level with the name) = **day** shift;
- **middle row** = **midshift** — the second half of a *split* day (e.g. `BC`
  then `T`); rare. When both top and middle are filled for a date, both shifts
  get `"split_day": true`;
- **bottom row** = **night** shift.

Other rules:

- short alphabetic tokens are shift codes; longer/free-text is captured as a
  **note**;
- a cell of **`no`** (or `no <code>`) is an **availability flag**: the person is
  not available / out sick that day. Those dates appear in the person's
  `unavailable` list, and any shift on that date is `"available": false` — the
  shift that needs covering when someone calls out;
- codes are **decoded** via `schedule_extractor/definitions.py` into a
  `category` (`location` / `status` / `unknown`) and a `meaning`
  (e.g. `BC` → Birth Center, `HC` → Hillcrest, `V` → Vacation, `R` → Request);
- **timings** are filled by location/level:
  - any **night** shift = `19:30`–`08:00` (crosses midnight)
  - **Birth Center** (`BC`) day = `07:30`–`20:00`; **Hillcrest** (`HC`) day = `07:00`–`19:30`
  - **Triage** (`T`) = `07:30`–`18:00`
  - **clinics** — everything that isn't BC or HC (`CV`, `VLJ`, `RB`, `MOS`, `ENC`) —
    run a **full day `08:00`–`17:00`**, unless the box's **center bar is coloured
    in** (a split), in which case the day row is the **morning** half
    (`08:00`–`12:00`) and the mid row is the **afternoon** half (`13:00`–`17:00`)
  - status/availability codes (`V`, `R`, `H`, `A`/`OK`, `no`) carry no clock window;
- a **green-filled `V`** is approved vacation → `"approved": true` (no fill →
  `false`).

Edit `definitions.py` to add codes, locations, or timing windows.

```bash
python -m schedule_extractor roster.xlsx --layout roster \
  --sheet "June 21 - July 18, 26" -o roster.json --pretty
```

Output (per person):

```json
{
  "name": "CHOI",
  "contact": ["C: 417-342-4960", "P: TXT TO CELL"],
  "shifts": [
    {"date": "2026-07-03", "code": "BC", "shift_type": "night",
     "category": "location", "meaning": "Birth Center",
     "start": "19:30", "end": "08:00", "crosses_midnight": true, "available": true}
  ],
  "unavailable": [],
  "notes": [{"date": null, "text": "Husband will be working ... Available for nights on 7/14"}]
}
```

Codes stay **raw** — mapping them to clock times (e.g. `BC` = 07:00–19:00 day /
19:00–07:00 night) is a later, user-supplied step. `--sheet` selects the tab and
`--year` provides the year if the sheet title lacks one.

## Scope / limitations

- Cell extraction is the primary, exact path.
- Image OCR reliably extracts and OCRs the picture to text; turning an arbitrary image
  *layout* back into a people-by-date grid is left for tuning against your real files
  (the raw OCR text is provided so you can build that mapping).
- Interpreting codes into shift times is intentionally out of scope.

## Layout

```
schedule_extractor/   package
  cli.py              argument parsing / entry point
  workbook.py         per-sheet routing (cells vs image)
  cell_extractor.py   grid heuristics -> people + shifts
  image_extractor.py  pull embedded images, hand to OCR
  ocr.py              Tesseract wrapper (graceful if missing)
  output.py           JSON serialization
  models.py           dataclasses
tools/make_sample.py  synthetic test workbook generator
tests/                pytest unit tests
```
