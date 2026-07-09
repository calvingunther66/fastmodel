import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Open-shift board (B1). Members see shifts that need covering and can claim the
// ones they're eligible for; coordinators (manage_coverage) approve a claimer.
export default function OpenShifts({ user, can, onChange }) {
  const [rows, setRows] = useState([]);
  const [swaps, setSwaps] = useState([]);
  const [err, setErr] = useState("");
  const isCoord = can("manage_coverage");
  const canSwaps = can("manage_swaps");

  function load() {
    api.openShifts().then(setRows).catch((e) => setErr(e.message));
    if (canSwaps) api.swaps().then(setSwaps).catch(() => {});
  }
  useEffect(load, []);

  function act(p) {
    p.then(() => { load(); onChange && onChange(); }).catch((e) => setErr(e.message));
  }

  const pendingSwaps = swaps.filter((s) => s.status === "accepted");

  if (err) return <p className="error">{err}</p>;

  function whenLabel(r) {
    const d = r.days_until;
    if (d === null || d === undefined) return "—";
    if (d < 0) return `${-d}d ago`;
    if (d === 0) return "today";
    if (d === 1) return "tomorrow";
    return `in ${d}d`;
  }

  return (
    <div className="open-shifts">
      {canSwaps && (
        <div className="swap-approvals">
          <h2>Swaps awaiting approval</h2>
          {pendingSwaps.length === 0
            ? <p className="muted">No accepted swaps waiting.</p>
            : (
              <ul className="offer-list">
                {pendingSwaps.map((s) => (
                  <li key={s.id}>
                    <span>{s.a_person} {s.a_date}({s.a_type}) ⇄ {s.b_person} {s.b_date}({s.b_type})</span>
                    <button className="primary small"
                      onClick={() => act(api.decideSwap(s.id, "approved"))}>approve</button>
                    <button className="ghost small danger"
                      onClick={() => act(api.decideSwap(s.id, "rejected"))}>reject</button>
                  </li>
                ))}
              </ul>
            )}
        </div>
      )}
      <h2>Open shifts {rows.length > 0 && <span className="count-badge">{rows.length}</span>}</h2>
      <p className="muted">Shifts someone has called out of that still need a cover.</p>
      {rows.length === 0 ? <p className="muted">No open shifts right now. 🎉</p> : (
      <table className="grid-table">
        <thead>
          <tr><th>When</th><th>Date</th><th>Shift</th><th>Out</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`urg-${r.urgency}`}>
              <td><span className={`urg-pill urg-${r.urgency}`}>{whenLabel(r)}</span></td>
              <td>{r.date}</td>
              <td>{r.code || "—"} <span className="muted">({r.shift_type})</span></td>
              <td>{r.name}</td>
              <td>
                {r.claimers?.length
                  ? <span>claimed by {r.claimers.join(", ")}</span>
                  : <span className="muted">unclaimed</span>}
              </td>
              <td>
                {user?.person && r.eligible && !r.claimed_by_me && (
                  <button onClick={() => act(api.claim(r.name, r.date, r.shift_type))}>
                    I can cover
                  </button>
                )}
                {user?.person && r.claimed_by_me && (
                  <button className="ghost"
                    onClick={() => act(api.unclaim(r.name, r.date, r.shift_type))}>
                    Withdraw
                  </button>
                )}
                {user?.person && !r.eligible && !isCoord && (
                  <span className="muted" title={r.eligibility}>not eligible</span>
                )}
                {isCoord && r.claimers?.map((c) => (
                  <button key={c} className="primary"
                    onClick={() => act(api.approveClaim(r.name, r.date, r.shift_type, c))}>
                    Approve {c}
                  </button>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
    </div>
  );
}
