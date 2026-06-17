"""Serialize an ExtractionResult to JSON (file or stdout)."""

from __future__ import annotations

import json
import sys

from .models import ExtractionResult


def to_json(result, pretty: bool = False) -> str:
    data = result.to_dict() if hasattr(result, "to_dict") else result
    return json.dumps(
        data,
        indent=2 if pretty else None,
        default=str,
        ensure_ascii=False,
    )


def write_json(result, path: str | None = None, pretty: bool = False) -> None:
    text = to_json(result, pretty=pretty)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
