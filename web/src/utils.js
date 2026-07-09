// Enumerate ISO dates from start..end inclusive.
export function dateRange(start, end) {
  if (!start || !end) return [];
  const out = [];
  const d = new Date(start + "T00:00:00");
  const last = new Date(end + "T00:00:00");
  while (d <= last) {
    out.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return out;
}

const WEEKDAY = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

export function dayLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return { dom: d.getDate(), dow: WEEKDAY[d.getDay()], weekend: d.getDay() === 0 || d.getDay() === 6 };
}

const KNOWN_LOCATIONS = new Set(["BC", "HC", "T", "CV", "VLJ", "MOS", "RB", "ENC", "NTAS"]);

// CSS class for a shift, based on its level / status. Day/mid shifts at a
// known location code get a location-specific color; night always reads as
// the night pill regardless of location.
export function shiftClass(s) {
  if (s.available === false) return "shift unavailable";
  if (s.shift_type === "night") return "shift night";
  if (s.code === "V") return s.approved ? "shift vacation-approved" : "shift vacation";
  if (KNOWN_LOCATIONS.has(s.code)) return `shift loc-${s.code}`;
  if (s.shift_type === "midshift") return "shift midshift";
  return "shift day";
}

export function timeLabel(s) {
  if (s.start && s.end) return `${s.start}–${s.end}${s.crosses_midnight ? " (+1)" : ""}`;
  return s.meaning || "";
}
