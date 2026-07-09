import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Unit holiday registry (H3). Marked dates highlight on the grid and feed the
// "worked a holiday" equity metric in Insights.
export default function Holidays({ onChange }) {
  const [holidays, setHolidays] = useState([]);
  const [date, setDate] = useState("");
  const [label, setLabel] = useState("");
  const [err, setErr] = useState("");

  function refresh() { api.holidays().then(setHolidays).catch((e) => setErr(e.message)); }
  useEffect(() => { refresh(); }, []);

  async function add(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.addHoliday(date, label);
      setDate(""); setLabel(""); refresh(); onChange && onChange();
    } catch (e2) { setErr(e2.message); }
  }

  async function remove(d) {
    setErr("");
    try { await api.removeHoliday(d); refresh(); onChange && onChange(); }
    catch (e2) { setErr(e2.message); }
  }

  return (
    <div className="card holidays">
      <h2>Holidays</h2>
      <p className="muted">
        Mark unit holidays. They’re highlighted on the schedule and counted as
        “worked a holiday” in Insights.
      </p>
      {err && <div className="error" role="alert">{err}</div>}
      <form className="row gap" onSubmit={add}>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required
          aria-label="Holiday date" />
        <input placeholder="label (e.g. July 4th)" value={label}
          onChange={(e) => setLabel(e.target.value)} aria-label="Holiday label" />
        <button>Add</button>
      </form>
      <ul className="callout-list">
        {holidays.map((h) => (
          <li key={h.date}>
            <span className="who">{h.date}</span>
            <span className="when">{h.label || "holiday"}</span>
            <button className="ghost small danger" onClick={() => remove(h.date)}>remove</button>
          </li>
        ))}
        {holidays.length === 0 && <li className="muted">No holidays marked.</li>}
      </ul>
    </div>
  );
}
