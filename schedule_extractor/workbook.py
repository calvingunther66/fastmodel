"""Top-level workbook orchestration: route each sheet to cells and/or OCR."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl

from .cell_extractor import extract_cells, has_cell_grid
from .image_extractor import extract_images
from .models import ExtractionResult, SheetResult
from .ocr import OcrEngine


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_workbook(
    path: str,
    *,
    header_row: int | None = None,
    name_col=None,
    image_dir: str = "extracted_images",
) -> ExtractionResult:
    """Extract schedule data from every sheet of an .xlsx workbook."""
    wb = openpyxl.load_workbook(path, data_only=True)
    result = ExtractionResult(source_file=str(Path(path)), extracted_at=_now_iso())
    ocr_engine = OcrEngine()

    for ws in wb.worksheets:
        images = list(getattr(ws, "_images", []) or [])
        source_types: list[str] = []

        if has_cell_grid(ws):
            sheet_res = extract_cells(ws, header_row=header_row, name_col=name_col)
            if sheet_res.people:
                source_types.append("cells")
        else:
            sheet_res = SheetResult(name=ws.title, source_type="empty")

        if images:
            source_types.append("image")
            result.images.extend(extract_images(ws, images, image_dir, ocr_engine))

        sheet_res.source_type = "+".join(source_types) if source_types else "empty"
        result.sheets.append(sheet_res)

    return result
