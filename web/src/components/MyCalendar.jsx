import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { timeLabel } from "../utils.js";

export default function MyCalendar({ schedule }) {
  const [people, setPeople] = useState([]);
  const [name, setName] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.people().then(setPeople).catch(() => setPeople([]));
  }, []);

  const me = people.find((p) => p.name === name);
  const myShifts = useMemo(() => {
    const person = (schedule?.people || []).find((p) => p.name === name);
    return person ? person.shifts : [];
  }, [schedule, name]);

  function copy() {
    navigator.clipboard?.writeText(me.ics_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const googleUrl = me
    ? `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(me.webcal_url)}`
    : "#";

  return (
    <div className="card">
      <h2>Your live calendar</h2>
      <p className="muted">
        Pick your name to get a calendar link you can subscribe to. It updates
        automatically whenever a new schedule is posted.
      </p>

      <label className="picker">
        I am:
        <select value={name} onChange={(e) => setName(e.target.value)}>
          <option value="">— choose your name —</option>
          {people.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name} ({p.shift_count})
            </option>
          ))}
        </select>
      </label>

      {me && (
        <div className="cal-link">
          <div className="row">
            <input readOnly value={me.ics_url} onFocus={(e) => e.target.select()} />
            <button onClick={copy}>{copied ? "Copied!" : "Copy link"}</button>
          </div>
          <div className="actions">
            <a href={me.webcal_url}>Subscribe (Apple/Outlook)</a>
            <a href={googleUrl} target="_blank" rel="noreferrer">
              Add to Google Calendar
            </a>
          </div>
          <p className="hint">
            Tip: in Google Calendar use “Other calendars → From URL” and paste the
            link above for an auto-refreshing subscription.
          </p>

          <h3>Upcoming shifts</h3>
          <ul className="shift-list">
            {myShifts.map((s, i) => (
              <li key={i} className={s.available === false ? "out" : ""}>
                <span className="d">{s.date}</span>
                <span className="c">{s.code}</span>
                <span className="m">{s.meaning || ""}</span>
                <span className="t">{timeLabel(s)}</span>
                {s.available === false && <span className="flag">needs coverage</span>}
              </li>
            ))}
            {!myShifts.length && <li className="muted">No shifts this period.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
