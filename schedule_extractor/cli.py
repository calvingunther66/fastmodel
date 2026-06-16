"""Command-line interface for the schedule extractor."""

from __future__ import annotations

import argparse
import sys

from .output import write_json
from .workbook import extract_workbook


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedule_extractor",
        description=(
            "Extract a person's schedule from an Excel workbook. Reads shift "
            "codes from cells, and OCRs embedded images. Outputs structured JSON "
            "of raw codes per person per date (no interpretation of codes)."
        ),
    )
    parser.add_argument("input", help="Path to the .xlsx file")
    parser.add_argument(
        "-o", "--output", help="Write JSON here (default: print to stdout)"
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=None,
        help="1-based row number of the date header (default: auto-detect)",
    )
    parser.add_argument(
        "--name-col",
        default=None,
        help="Name column as a letter or 1-based number (default: auto-detect)",
    )
    parser.add_argument(
        "--image-dir",
        default="extracted_images",
        help="Directory to save extracted images (default: extracted_images)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print the JSON output"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = extract_workbook(
            args.input,
            header_row=args.header_row,
            name_col=args.name_col,
            image_dir=args.image_dir,
        )
    except FileNotFoundError:
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 1
    write_json(result, args.output, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
