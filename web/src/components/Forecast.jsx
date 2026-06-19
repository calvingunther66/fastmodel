import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Coverage gap forecaster (K2): upcoming days that are under-staffed (gap) or met
// with no qualified backup free (thin).
export default function Forecast() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { api.forecast().then(setData).catch((e) => setErr(e.message)); }, []);

  if (err) return <div className="card"><div className="error" role="alert">{err}</div></div>;
  if (!data) return null;

  const { days, summary } = data;
  return (
    <div className="card forecast">
      <h2>Coverage forecast</h2>
      <p className="muted">
        Upcoming risk against the daily coverage targets:{" "}
        <strong>{summary.gap_days}</strong> day(s) under-staffed,{" "}
        <strong>{summary.thin_days}</strong> with no qualified backup.
      </p>
      {days.length === 0
        ? <p className="muted">No coverage risks ahead. 🎉</p>
        : (
          <ul className="callout-list">
            {days.map((d) => (
              <li key={d.date}>
                <span className="who">{d.date}</span>
                <span className={`urg-pill urg-${d.risk === "gap" ? "urgent" : "soon"}`}>
                  {d.risk === "gap" ? "gap" : "thin"}
                </span>
                <span className="muted">{d.issues.map((i) => i.message).join(" · ")}</span>
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}
