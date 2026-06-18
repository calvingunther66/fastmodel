"""Staff roster: the master list of people and their work attributes.

For now this is **placeholder data** so the schedule-creation workflow is usable
end-to-end. It will be replaced by the real roster the owner provides: per person,
the clinics they're qualified for, whether they're career or per-diem, whether they
have seniority, and whether they work nights.

Stored in DATA_DIR/roster.json. When the real list arrives, POST it to /api/roster
(or drop it in the file) and `placeholder` flips to false.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import DATA_DIR

# Placeholder staff (clinic codes match schedule_extractor.definitions).
_PLACEHOLDER = [
    {"name": "DOE, JANE", "clinics": ["BC", "HC", "CV"], "employment": "career",
     "seniority": True, "works_nights": False},
    {"name": "SMITH, ALEX", "clinics": ["BC", "T"], "employment": "career",
     "seniority": False, "works_nights": True},
    {"name": "LEE, SAM", "clinics": ["HC", "MOS", "VLJ"], "employment": "per_diem",
     "seniority": False, "works_nights": True},
    {"name": "PATEL, RAVI", "clinics": ["BC", "ENC"], "employment": "career",
     "seniority": True, "works_nights": False},
    {"name": "GARCIA, MARIA", "clinics": ["CV", "RB", "MOS"], "employment": "per_diem",
     "seniority": False, "works_nights": True},
    {"name": "NGUYEN, KIM", "clinics": ["BC", "HC", "T", "CV"], "employment": "career",
     "seniority": False, "works_nights": True},
]

EMPLOYMENT = ["career", "per_diem"]


class StaffRoster:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.path = data_dir / "roster.json"
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"staff": _PLACEHOLDER, "placeholder": True})

    def _read(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"staff": [], "placeholder": True}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def list(self) -> list[dict]:
        return self._read().get("staff", [])

    def is_placeholder(self) -> bool:
        return self._read().get("placeholder", False)

    def quals(self) -> dict:
        """Map of UPPERCASED name -> qualification metadata, for the engine.

        {NAME: {clinics: set[str], works_nights: bool, employment: str,
                seniority: bool}}. Names are uppercased so they line up with the
        schedule's (uppercase) person names.
        """
        out: dict[str, dict] = {}
        for s in self.list():
            name = str(s.get("name", "")).strip()
            if not name:
                continue
            out[name.upper()] = {
                "clinics": {str(c).upper() for c in (s.get("clinics") or [])},
                "works_nights": bool(s.get("works_nights", True)),
                "employment": s.get("employment", "career"),
                "seniority": bool(s.get("seniority", False)),
            }
        return out

    def engine_quals(self) -> dict | None:
        """Quals for the coverage/validator engines, or None while placeholder so
        the engines fall back to the history heuristic (nothing breaks pre-roster)."""
        return None if self.is_placeholder() else self.quals()

    def replace(self, staff: list[dict]) -> list[dict]:
        clean = []
        for s in staff:
            if not s.get("name"):
                continue
            clean.append({
                "name": str(s["name"]).strip(),
                "clinics": [str(c).upper() for c in (s.get("clinics") or [])],
                "employment": s.get("employment") if s.get("employment") in EMPLOYMENT else "career",
                "seniority": bool(s.get("seniority")),
                "works_nights": bool(s.get("works_nights", True)),
            })
        with self._lock:
            self._write({"staff": clean, "placeholder": False})
        return clean
