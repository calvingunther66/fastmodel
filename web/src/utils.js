// Format a Date as an ISO day using its *local* parts. toISOString() would
// convert to UTC first, which shifts the day back for anyone east of UTC.
function isoDay(d) {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

// Enumerate ISO dates from start..end inclusive.
export function dateRange(start, end) {
  if (!start || !end) return [];
  const out = [];
  const d = new Date(start + "T00:00:00");
  const last = new Date(end + "T00:00:00");
  while (d <= last) {
    out.push(isoDay(d));
    d.setDate(d.getDate() + 1);
  }
  return out;
}

const WEEKDAY = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

export function dayLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return { dom: d.getDate(), dow: WEEKDAY[d.getDay()], weekend: d.getDay() === 0 || d.getDay() === 6 };
}

const KNOWN_LOCATIONS = new Set(["BC", "HC", "T", "APP", "CNV", "VLJ", "MOS", "RB", "ENC", "NTAS"]);

// Alternate spellings, folded onto the code the stylesheet has a colour for.
// Mirrors CODE_ALIASES in schedule_extractor/definitions.py.
const CODE_ALIASES = { CV: "CNV" };

// CSS class for a shift, based on its level / status. Day/mid shifts at a
// known location code get a location-specific color; night always reads as
// the night pill regardless of location.
export function shiftClass(s) {
  // Codes are hand-typed, so normalise before matching: a lowercase "v" used to
  // fall through every branch below and render a vacation as a working day.
  const raw = (s.code || "").trim().toUpperCase();
  const code = CODE_ALIASES[raw] || raw;
  if (s.available === false) return "shift unavailable";
  if (s.shift_type === "night") return "shift night";
  if (code === "V") return s.approved ? "shift vacation-approved" : "shift vacation";
  if (KNOWN_LOCATIONS.has(code)) return `shift loc-${code}`;
  if (s.shift_type === "midshift") return "shift midshift";
  return "shift day";
}

export function timeLabel(s) {
  if (s.start && s.end) return `${s.start}–${s.end}${s.crosses_midnight ? " (+1)" : ""}`;
  return s.meaning || "";
}
