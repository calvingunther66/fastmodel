"""Thin wrapper around Tesseract OCR that degrades gracefully when it's absent.

If the ``tesseract`` binary (or the ``pytesseract`` package) is missing, the
engine reports ``available = False`` and callers skip OCR while still saving the
extracted image to disk. This keeps the tool usable without OCR installed.
"""

from __future__ import annotations

import shutil


class OcrEngine:
    def __init__(self) -> None:
        self.binary_path = shutil.which("tesseract")
        self.available = self.binary_path is not None
        self._pytesseract = None
        if self.available:
            try:
                import pytesseract

                self._pytesseract = pytesseract
            except ImportError:
                self.available = False

    def image_to_text(self, pil_image) -> str | None:
        """Return OCR text, or None if OCR is unavailable or failed."""
        if not self.available or self._pytesseract is None:
            return None
        try:
            return self._pytesseract.image_to_string(pil_image)
        except Exception:
            return None
