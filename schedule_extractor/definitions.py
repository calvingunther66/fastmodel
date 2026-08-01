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
    "CNV": "Convoy",         # how the real workbooks spell it
    "CV": "Convoy",          # older/short spelling, kept as an alias
    "VLJ": "Villa La Jolla",
    "MOS": "Medical Office South",
    "T": "Triage",
    "APP": "LJ OBGYN APP C (Triage/PP)",   # legend: 6:30a-7p, weekends
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

# Alternate spellings seen across workbooks, mapped to the spelling the sheets
# actually use. Comparing a roster's clinics against a schedule's codes only
# works if both sides agree, so normalise before matching.
CODE_ALIASES = {"CV": "CNV"}

# Anything that isn't the Birth Center or Hillcrest is a "clinic" and runs a
# standard full day unless the box's center bar is coloured in (a split).
# CLINIC_CODES is the canonical list to offer in pickers and generate from;
# CLINICS also accepts the aliases, for recognising what's already in a file.
CLINIC_CODES = ["CNV", "VLJ", "RB", "MOS", "ENC"]
CLINICS = set(CLINIC_CODES) | {"CV"}

# Shift windows. (start, end, crosses_midnight)
NIGHT_WINDOW = ("19:30", "08:00", True)     # any night row (legend: 7:30p-8a)
TRIAGE_WINDOW = ("07:30", "18:00", False)   # T (legend: 7:30a-6p)
BC_DAY_WINDOW = ("07:30", "20:00", False)   # Birth Center day (legend: 7:30a-8p)
HC_DAY_WINDOW = ("07:00", "19:30", False)   # Hillcrest day (legend: 7:00a-7:30p)
CLINIC_DAY_WINDOW = ("08:00", "17:00", False)        # full clinic day
CLINIC_MORNING_WINDOW = ("08:00", "12:00", False)    # split: morning half
CLINIC_AFTERNOON_WINDOW = ("13:00", "17:00", False)  # split: afternoon half
APP_DAY_WINDOW = ("06:30", "19:00", False)           # APP (legend: 6:30a-7p Wkend)

# Row offset within a person's 3-row block -> shift level.
OFFSET_LEVEL = {0: "day", 1: "midshift", 2: "night"}

# Case-insensitive lookups. The workbook is hand-typed, so the same code turns up
# as "BC"/"bc" and "BDay"/"bday"; matching on the upper-cased token keeps every
# spelling pointing at one definition.
_STATUS_UPPER = {k.upper(): v for k, v in STATUS.items()}
_LOCATIONS_UPPER = {k.upper(): v for k, v in LOCATIONS.items()}


def decode(code: str) -> dict:
    """Return {'category', 'meaning'} for a raw code (category may be 'unknown')."""
    upper = code.strip().upper()
    if upper in _STATUS_UPPER:
        return {"category": "status", "meaning": _STATUS_UPPER[upper]}
    if upper in _LOCATIONS_UPPER:
        return {"category": "location", "meaning": _LOCATIONS_UPPER[upper]}
    return {"category": "unknown", "meaning": None}


def is_known(code: str) -> bool:
    """True if the token is a defined status or location code."""
    return decode(code)["category"] != "unknown"


def canonical_code(code: str) -> str:
    """Upper-case a code and fold any alternate spelling onto the canonical one."""
    upper = (code or "").strip().upper()
    return CODE_ALIASES.get(upper, upper)


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
    if upper == "APP":
        return APP_DAY_WINDOW
    if upper == "BC":
        return BC_DAY_WINDOW
    if upper == "HC":
        return HC_DAY_WINDOW
    if upper in CLINICS:
        if shift_type == "midshift":
            return CLINIC_AFTERNOON_WINDOW
        return CLINIC_MORNING_WINDOW if split else CLINIC_DAY_WINDOW
    return (None, None, False)  # unknown / undefined timing


# Theme indices 0 and 1 are the workbook's light/dark *background* colours (white
# and black in the default theme) — the same neutrals `has_solid_fill` ignores.
_NEUTRAL_THEMES = {0, 1}


def _fill_rgb(cell) -> str | None:
    """The 6-hex-digit RGB of a cell's solid fill, or None.

    Returns None for a theme- or index-based fill: those can't be resolved to RGB
    without the workbook's theme/palette, so callers must not read a colour into
    them. Use `fill_key` when all you need is to tell two fills apart.
    """
    fill = getattr(cell, "fill", None)
    if not fill or fill.patternType != "solid":
        return None
    colour = fill.fgColor
    if getattr(colour, "type", None) != "rgb":
        return None
    rgb = colour.rgb
    if not isinstance(rgb, str) or len(rgb) < 6:
        return None
    return rgb[-6:].upper()  # strip the alpha prefix


def fill_key(cell):
    """A hashable identity for a cell's solid fill, or None if it has none.

    Unlike `has_solid_fill` this keeps neutral (white/black) fills, because the
    point is to compare one cell's fill against another's — the workbook draws a
    person's day box by filling two rows the *same* colour, and shades whole
    weekend columns, so telling "same fill" from "different fill" is what
    separates real markup from background styling.
    """
    fill = getattr(cell, "fill", None)
    if not fill or fill.patternType != "solid":
        return None
    colour = fill.fgColor
    kind = getattr(colour, "type", None)
    if kind == "rgb":
        rgb = _fill_rgb(cell)
        return ("rgb", rgb) if rgb else None
    if kind == "theme":
        theme = getattr(colour, "theme", None)
        if not isinstance(theme, int):
            return None
        tint = getattr(colour, "tint", 0.0)
        return ("theme", theme, round(tint if isinstance(tint, float) else 0.0, 4))
    if kind == "indexed":
        idx = getattr(colour, "indexed", None)
        return ("indexed", idx) if isinstance(idx, int) else None
    return None


def has_solid_fill(cell) -> bool:
    """True if a cell has a solid fill in some non-neutral colour.

    Handles theme- and index-based fills too; only `patternType == "solid"` with
    an actual colour counts, and plain white/black are treated as "no fill".
    """
    key = fill_key(cell)
    if key is None:
        return False
    if key[0] == "rgb":
        return key[1] not in ("FFFFFF", "000000")
    if key[0] == "theme":
        return key[1] not in _NEUTRAL_THEMES
    return True


def is_green_fill(cell) -> bool:
    """True if a cell has a green fill (e.g. approved vacation).

    Only an explicit RGB fill can answer this — a theme fill has no resolvable
    colour here, so it is reported as not-green rather than guessed at.
    """
    hexpart = _fill_rgb(cell)
    if not hexpart:
        return False
    try:
        r, g, b = int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16)
    except ValueError:
        return False
    return g > r and g > b and g >= 0x80
