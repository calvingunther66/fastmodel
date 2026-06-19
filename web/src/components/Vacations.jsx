import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Vacation-approval review (H1). The workbook marks approved time off with a green
// fill; here a coordinator confirms pending requests or overrides a decision.
const STATUS_LABEL = { approved: "Approved", denied: "Denied", pending: "Pending" };

export default function Vacations({ onChange }) {
  const [vacs, setVacs] = useState([]);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("all");

  function refresh() {
    api.vacations().then(setVacs).catch((e) => setErr(e.message));
  }
  useEffect(() => { refresh(); }, []);

  async function decide(v, status) {
    setErr("");
    try {
      // Toggle off if clicking the active status (back to pending).
      const next = v.status === status ? "pending" : status;
      await api.decideVacation(v.person, v.date, next);
      refresh();
      onChange && onChange();
    } catch (e) { setErr(e.message); }
  }

  const shown = vacs.filter((v) => filter === "all" || v.status === filter);
  const counts = vacs.reduce((acc, v) => { acc[v.status] = (acc[v.status] || 0) + 1; return acc; }, {});

  return (
    <div className="card vacations">
      <h2>Vacation requests</h2>
      <p className="muted">
        Approve or deny time off. Approved vacation blocks the generator from
        scheduling that person and shows green on the grid.
      </p>
      {err && <div className="error" role="alert">{err}</div>}
      <div className="row gap" style={{ marginBottom: 10 }}>
        {["all", "pending", "approved", "denied"].map((f) => (
          <button key={f} className={`ghost small${filter === f ? " on" : ""}`}
            onClick={() => setFilter(f)}>
            {f === "all" ? "All" : STATUS_LABEL[f]}
            {f !== "all" && counts[f] ? ` (${counts[f]})` : ""}
          </button>
        ))}
      </div>
      {shown.length === 0 && <p className="muted">No vacation entries{filter !== "all" ? ` (${filter})` : ""}.</p>}
      <ul className="callout-list">
        {shown.map((v) => (
          <li key={`${v.person}|${v.date}`}>
            <span className="who">{v.person}</span>
            <span className="when">{v.date}</span>
            <span className={`vac-pill vac-${v.status}`}>{STATUS_LABEL[v.status]}</span>
            {v.from_workbook && v.status === "approved" && !v.decision &&
              <span className="muted small">from workbook</span>}
            <span className="row gap">
              <button className="ghost small" onClick={() => decide(v, "approved")}>approve</button>
              <button className="ghost small danger" onClick={() => decide(v, "denied")}>deny</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
