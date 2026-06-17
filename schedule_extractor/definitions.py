"""Code, location, and shift-timing definitions for the roster.

These come from the schedule owner. Anything not listed here is preserved
verbatim with ``category = "unknown"`` so it is never silently dropped.

Timing notes (from the owner):
* Night shift: 19:30 -> 08:00 (next day). Applies to any code on the night row.
* Triage (T): 07:30 -> 18:00.
* Day-shift length varies by location/assignment, so day start/end are left null
  until a per-location day-hours table is provided.
"""

from __future__ import annotations

# Location / assignment codes (where the person is working that shift).
LOCATIONS = {
    "BC": "Birth Center",
    "HC": "Hillcrest",
    "CV": "Convoy",
    "VLJ": "Villa La Jolla",
    "MOS": "Medical Office South",
    "T": "Triage",
    "RB": "RB / Vía Tizón",
    "ENC": "Encinitas",      # night code (full name unconfirmed)
    "NTAS": "NTAS",          # night code (full name unconfirmed)
}

# Status / availability markers (not a specific worked location).
STATUS = {
    "V": "Vacation",
    "R": "Request (requested day)",
    "BDay": "Birthday request (off)",
    "no": "Unavailable / out sick",
    "H": "Holiday",
    "A": "Available / on-call pool",
}

# Fixed shift windows we can state confidently. (start, end, crosses_midnight)
NIGHT_WINDOW = ("19:30", "08:00", True)
TRIAGE_WINDOW = ("07:30", "18:00", False)

# Row offset within a person's 3-row block -> shift level.
OFFSET_LEVEL = {0: "day", 1: "midshift", 2: "night"}


def decode(code: str) -> dict:
    """Return {'category', 'meaning'} for a raw code (category may be 'unknown')."""
    key = code.strip()
    if key in LOCATIONS:
        return {"category": "location", "meaning": LOCATIONS[key]}
    if key in STATUS:
        return {"category": "status", "meaning": STATUS[key]}
    # case-insensitive fallback (e.g. 'bc')
    upper = key.upper()
    if upper in LOCATIONS:
        return {"category": "location", "meaning": LOCATIONS[upper]}
    return {"category": "unknown", "meaning": None}


def shift_window(code: str, shift_type: str):
    """(start, end, crosses_midnight) for a shift, or (None, None, False) if variable.

    Time-off markers carry no clock window.
    """
    key = code.strip()
    if key in STATUS:
        return (None, None, False)
    if shift_type == "night":
        return NIGHT_WINDOW
    if key.upper() == "T":
        return TRIAGE_WINDOW
    return (None, None, False)  # day length is location-dependent / not yet defined


def is_green_fill(cell) -> bool:
    """True if a cell has a green fill (e.g. approved vacation)."""
    fill = getattr(cell, "fill", None)
    if not fill or fill.patternType != "solid":
        return False
    rgb = getattr(fill.fgColor, "rgb", None)
    if not isinstance(rgb, str) or len(rgb) < 6:
        return False
    hexpart = rgb[-6:]  # strip alpha
    try:
        r, g, b = int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16)
    except ValueError:
        return False
    return g > r and g > b and g >= 0x80
