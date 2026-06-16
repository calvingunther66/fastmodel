"""Schedule Extractor — extract a person's schedule from an Excel workbook.

Reads shift codes directly from spreadsheet cells, and falls back to OCR for
sheets whose schedule is an embedded image. Emits structured JSON of raw codes
per person per date. Interpretation of what each code means (shift timings) is
intentionally left to a later step.
"""

__version__ = "0.1.0"
