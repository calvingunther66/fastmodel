"""Build a per-person iCalendar (.ics) feed from their extracted shifts.

Timed shifts (with start/end) become timed events in the configured timezone,
with night shifts ending the next morning. Time-off / availability markers
(V, R, H, A/OK) become all-day events so the person sees their full picture.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event


def _hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def build_ics(person_name: str, shifts: list[dict], tz_name: str,
              reminder_minutes: int = 0) -> bytes:
    tz = ZoneInfo(tz_name)
    now = dt.datetime.now(tz)

    cal = Calendar()
    cal.add("prodid", "-//fastmodel//schedule//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{person_name} — Work Schedule")
    cal.add("x-wr-timezone", tz_name)

    for s in shifts:
        y, mo, d = (int(x) for x in s["date"].split("-"))
        day = dt.date(y, mo, d)
        code = s.get("code", "")
        meaning = s.get("meaning")
        shift_type = s.get("shift_type", "")

        ev = Event()
        ev.add("uid", f"{person_name}-{s['date']}-{code}-{shift_type}@fastmodel")
        ev.add("dtstamp", now)

        label = code if not meaning else f"{code} — {meaning}"

        if s.get("start") and s.get("end"):
            sh, sm = _hm(s["start"])
            eh, em = _hm(s["end"])
            start_dt = dt.datetime(y, mo, d, sh, sm, tzinfo=tz)
            end_dt = dt.datetime(y, mo, d, eh, em, tzinfo=tz)
            if s.get("crosses_midnight"):
                end_dt += dt.timedelta(days=1)
            ev.add("dtstart", start_dt)
            ev.add("dtend", end_dt)
            ev.add("summary", f"{label} ({shift_type})")
            # A real location helps phones group/colour shifts (D3).
            if meaning and s.get("category") == "location":
                ev.add("location", meaning)
            ev.add("categories", [shift_type or "shift"])
            # Optional reminder before a timed shift (per-person preference).
            if reminder_minutes and reminder_minutes > 0:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"{label} ({shift_type})")
                alarm.add("trigger", dt.timedelta(minutes=-reminder_minutes))
                ev.add_component(alarm)
        else:
            # All-day marker (vacation, holiday, request, available, …)
            ev.add("dtstart", day)
            ev.add("dtend", day + dt.timedelta(days=1))
            ev.add("summary", label)

        if s.get("covering_for"):
            ev["summary"] = f"{label} ({shift_type}) — covering for {s['covering_for']}"

        desc = []
        if s.get("covering_for"):
            desc.append(f"Covering for {s['covering_for']}")
        if s.get("available") is False:
            desc.append("⚠ Marked unavailable / called out — needs coverage")
        if s.get("approved") is True:
            desc.append("Vacation approved")
        elif s.get("approved") is False:
            desc.append("Vacation not yet approved")
        if s.get("split_day"):
            desc.append("Split day")
        if desc:
            ev.add("description", "; ".join(desc))

        cal.add_component(ev)

    return cal.to_ical()
