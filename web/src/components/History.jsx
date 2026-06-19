import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import ScheduleGrid from "./ScheduleGrid.jsx";

// Schedule history (M1): browse archived periods; re-uploads no longer destroy
// past months. Those with upload rights can re-activate an old period.
export default function History({ can, onChange }) {
  const [rows, setRows] = useState([]);
  const [sel, setSel] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [err, setErr] = useState("");
  const canActivate = can && can("upload");

  function refresh() { api.archive().then(setRows).catch((e) => setErr(e.message)); }
  useEffect(refresh, []);

  function open(period) {
    setSel(period); setViewing(null); setErr("");
    api.archiveView(period).then(setViewing).catch((e) => setErr(e.message));
  }

  function activate(period) {
    if (!confirm(`Make ${period} the active schedule? The current one stays archived.`)) return;
    api.archiveActivate(period)
      .then(() => { refresh(); onChange && onChange(); })
      .catch((e) => setErr(e.message));
  }

  return (
    <div className="card history">
      <h2>Schedule history</h2>
      <p className="muted">
        Every uploaded or created period is kept here, so re-uploads never lose
        past months.
      </p>
      {err && <div className="error" role="alert">{err}</div>}
      {rows.length === 0 && <p className="muted">No archived periods yet.</p>}
      <ul className="callout-list">
        {rows.map((r) => (
          <li key={r.period}>
            <span className="who">{r.period.replace("..", " → ")}</span>
            {r.active && <span className="vac-pill vac-approved">active</span>}
            <span className="muted">{r.parsed_sheet} · {r.people} people</span>
            <span className="row gap">
              <button className="ghost small" onClick={() => open(r.period)}>view</button>
              {canActivate && !r.active &&
                <button className="ghost small" onClick={() => activate(r.period)}>make active</button>}
            </span>
          </li>
        ))}
      </ul>

      {viewing && (
        <div className="archive-view">
          <h3>{sel?.replace("..", " → ")}</h3>
          <ScheduleGrid schedule={viewing} />
        </div>
      )}
    </div>
  );
}
