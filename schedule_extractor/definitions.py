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
    "OK": "Available / on-call pool",   # OK is an alias for A
}

# Anything that isn't the Birth Center or Hillcrest is a "clinic" and runs a
# standard full day unless the box's center bar is coloured in (a split).
CLINICS = {"CV", "VLJ", "RB", "MOS", "ENC"}

# Shift windows. (start, end, crosses_midnight)
NIGHT_WINDOW = ("19:30", "08:00", True)     # any night row (legend: 7:30p-8a)
TRIAGE_WINDOW = ("07:30", "18:00", False)   # T (legend: 7:30a-6p)
BC_DAY_WINDOW = ("07:30", "20:00", False)   # Birth Center day (legend: 7:30a-8p)
HC_DAY_WINDOW = ("07:00", "19:30", False)   # Hillcrest day (legend: 7:00a-7:30p)
CLINIC_DAY_WINDOW = ("08:00", "17:00", False)        # full clinic day
CLINIC_MORNING_WINDOW = ("08:00", "12:00", False)    # split: morning half
CLINIC_AFTERNOON_WINDOW = ("13:00", "17:00", False)  # split: afternoon half

# Row offset within a person's 3-row block -> shift level.
OFFSET_LEVEL = {0: "day", 1: "midshift", 2: "night"}


def decode(code: str) -> dict:
    """Return {'category', 'meaning'} for a raw code (category may be 'unknown')."""
    key = code.strip()
    upper = key.upper()
    if key in STATUS or upper in STATUS:
        return {"category": "status", "meaning": STATUS.get(key, STATUS.get(upper))}
    if key in LOCATIONS or upper in LOCATIONS:
        return {"category": "location", "meaning": LOCATIONS.get(key, LOCATIONS.get(upper))}
    return {"category": "unknown", "meaning": None}


def shift_window(code: str, shift_type: str, split: bool = False):
    """(start, end, crosses_midnight) for a shift, or (None, None, False).

    Status/time-off markers carry no clock window. Nights are fixed. Days depend
    on location; clinics are a full day unless `split`, in which case the day row
    is the morning half and the mid row is the afternoon half.
    """
    if decode(code)["category"] == "status":
        return (None, None, False)

    upper = code.strip().upper()
    if shift_type == "night":
        return NIGHT_WINDOW
    if upper == "T":
        return TRIAGE_WINDOW
    if upper == "BC":
        return BC_DAY_WINDOW
    if upper == "HC":
        return HC_DAY_WINDOW
    if upper in CLINICS:
        if shift_type == "midshift":
            return CLINIC_AFTERNOON_WINDOW
        return CLINIC_MORNING_WINDOW if split else CLINIC_DAY_WINDOW
    return (None, None, False)  # unknown / undefined timing


def has_solid_fill(cell) -> bool:
    """True if a cell has any non-empty solid fill (e.g. a coloured center bar)."""
    fill = getattr(cell, "fill", None)
    if not fill or fill.patternType != "solid":
        return False
    rgb = getattr(fill.fgColor, "rgb", None)
    if not isinstance(rgb, str) or len(rgb) < 6:
        return False
    return rgb[-6:].upper() not in ("FFFFFF", "000000")


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
