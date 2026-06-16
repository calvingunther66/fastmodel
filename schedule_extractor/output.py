"""Serialize an ExtractionResult to JSON (file or stdout)."""

from __future__ import annotations

import json
import sys

from .models import ExtractionResult


def to_json(result: ExtractionResult, pretty: bool = False) -> str:
    return json.dumps(
        result.to_dict(),
        indent=2 if pretty else None,
        default=str,
        ensure_ascii=False,
    )


def write_json(result: ExtractionResult, path: str | None = None, pretty: bool = False) -> None:
    text = to_json(result, pretty=pretty)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
