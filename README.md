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
