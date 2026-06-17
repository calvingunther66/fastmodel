import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Dashboard for admins / coordinators: who steps up to cover the most, plus each
// person's work mix. The recommender deliberately spreads the next ask around, so
// this celebrates the reliable folks while the model gives others a turn.
export default function Insights() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.leaderboard().then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="card"><div className="error">{err}</div></div>;
  if (!data) return <div className="card muted">Loading…</div>;

  const people = data.people || [];
  const maxCovers = Math.max(1, ...people.map((p) => p.covers));

  const breakdown = (obj) =>
    Object.entries(obj || {}).sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}×${v}`).join("  ") || "—";

  return (
    <div className="card">
      <h2>Step-up dashboard</h2>
      <p className="muted">
        Ranked by how often each person has covered a call-out
        {data.periods ? ` · learned from ${data.periods} schedule period${data.periods === 1 ? "" : "s"}` : ""}.
        The coverage recommender uses this to <strong>balance the load</strong> —
        frequent coverers get a rest, others get a turn.
      </p>
      <table className="board">
        <thead>
          <tr>
            <th>#</th><th>Person</th><th>Covers</th><th>Cover types</th>
            <th>Shifts worked</th><th>Work mix</th>
          </tr>
        </thead>
        <tbody>
          {people.map((p, i) => (
            <tr key={p.name}>
              <td className="rank">{i + 1}</td>
              <td className="board-name">{p.name}</td>
              <td>
                <div className="bar-wrap">
                  <div className="bar" style={{ width: `${(p.covers / maxCovers) * 100}%` }} />
                  <span className="bar-num">{p.covers}</span>
                </div>
              </td>
              <td className="mix">{breakdown(p.covers_by_type)}</td>
              <td>{p.worked_total}</td>
              <td className="mix">{breakdown(p.worked_by_code)}</td>
            </tr>
          ))}
          {people.length === 0 && (
            <tr><td colSpan={6} className="muted">No history yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
