"""Data models for extracted schedule data.

Everything here is deliberately "raw": a shift is just a date key plus the
verbatim code found in the workbook. No code is interpreted into a shift time —
that mapping is supplied by the user in a later step.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Shift:
    """A single cell of schedule data: one person, one date, one raw code."""

    date: str          # ISO "YYYY-MM-DD" when derivable, else the raw header label
    raw_code: str      # verbatim text from the cell, e.g. "D", "N", "OFF", "12-8"


@dataclass
class Person:
    """One person (row) and their shifts across the date axis."""

    name: str
    shifts: list[Shift] = field(default_factory=list)


@dataclass
class SheetResult:
    """Extraction result for one worksheet's cell grid."""

    name: str
    source_type: str = "empty"   # "cells", "image", "cells+image", or "empty"
    date_axis: list[str] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImageResult:
    """Result of pulling (and OCR'ing) one embedded image."""

    sheet: str
    file: str
    ocr_available: bool
    ocr_text: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Top-level result for an entire workbook."""

    source_file: str
    extracted_at: str
    sheets: list[SheetResult] = field(default_factory=list)
    images: list[ImageResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
