"""Pull embedded images out of a worksheet and OCR them.

Each image is always saved to ``image_dir`` so it can be inspected by hand.
OCR text is added when a Tesseract engine is available. Turning an arbitrary
image *layout* back into a people-by-date grid is left for tuning against real
files; for now we capture the raw OCR text.
"""

from __future__ import annotations

import io
import os
import re

from .models import ImageResult
from .ocr import OcrEngine


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "sheet"


def _image_bytes(img) -> bytes | None:
    """Best-effort extraction of raw bytes from an openpyxl image object."""
    # openpyxl loads embedded images with a callable that returns the bytes.
    data_attr = getattr(img, "_data", None)
    if callable(data_attr):
        try:
            return data_attr()
        except Exception:
            pass
    elif isinstance(data_attr, (bytes, bytearray)):
        return bytes(data_attr)

    ref = getattr(img, "ref", None)
    if isinstance(ref, (bytes, bytearray)):
        return bytes(ref)
    if hasattr(ref, "read"):
        try:
            ref.seek(0)
            return ref.read()
        except Exception:
            return None
    return None


def extract_images(ws, images, image_dir: str, ocr_engine: OcrEngine) -> list[ImageResult]:
    os.makedirs(image_dir, exist_ok=True)
    results: list[ImageResult] = []

    for index, img in enumerate(images, start=1):
        warnings: list[str] = []
        ocr_text = ""
        filename = os.path.join(image_dir, f"{_safe(ws.title)}_{index}.png")
        data = _image_bytes(img)

        if data is None:
            warnings.append("could not read image bytes from workbook")
        else:
            try:
                from PIL import Image

                pil = Image.open(io.BytesIO(data))
                pil.save(filename)
                if ocr_engine.available:
                    text = ocr_engine.image_to_text(pil)
                    ocr_text = text or ""
                    if not ocr_text.strip():
                        warnings.append("OCR returned no text")
                else:
                    warnings.append("tesseract not installed; image saved without OCR")
            except Exception as exc:  # noqa: BLE001 - prototype: report and continue
                warnings.append(f"image processing failed: {exc}")

        results.append(
            ImageResult(
                sheet=ws.title,
                file=filename,
                ocr_available=ocr_engine.available,
                ocr_text=ocr_text,
                warnings=warnings,
            )
        )

    return results
