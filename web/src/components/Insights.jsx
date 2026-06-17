import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Dashboard for admins / coordinators. The leaderboard (who steps up most) and
// the scoring slider are gated by separate capabilities, so each can be delegated
// independently: view_leaderboard to see the board, tune_scoring to move the dial.
export default function Insights({ can }) {
  const showBoard = can("view_leaderboard");
  const showTuner = can("tune_scoring");

  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [weight, setWeight] = useState(0.5);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (showBoard) api.leaderboard().then(setData).catch((e) => setErr(e.message));
    if (showTuner) api.coverageSettings().then((s) => setWeight(s.fairness_weight)).catch(() => {});
  }, [showBoard, showTuner]);

  async function commit(v) {
    setWeight(v);
    try {
      await api.setCoverageSettings(v);
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
    } catch (e) { setErr(e.message); }
  }

  const people = data?.people || [];
  const maxCovers = Math.max(1, ...people.map((p) => p.covers));
  const breakdown = (obj) =>
    Object.entries(obj || {}).sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}×${v}`).join("  ") || "—";

  return (
    <div className="card">
      <h2>Step-up dashboard</h2>
      {err && <div className="error">{err}</div>}

      {showTuner && (
        <div className="tuner">
          <h3>Scoring dial <span className="trial">tune_scoring</span></h3>
          <p className="muted">
            How the coverage recommender weighs <strong>competence</strong> (who
            knows the role / works it often) against <strong>fairness</strong>
            (spreading cover duty so the willing few don’t burn out).
          </p>
          <div className="slider-row">
            <span>Competence</span>
            <input type="range" min="0" max="1" step="0.05" value={weight}
              onChange={(e) => setWeight(parseFloat(e.target.value))}
              onMouseUp={(e) => commit(parseFloat(e.target.value))}
              onTouchEnd={(e) => commit(parseFloat(e.target.value))} />
            <span>Fairness</span>
            <span className="slider-val">{Math.round(weight * 100)}% fair{saved ? " ✓" : ""}</span>
          </div>
        </div>
      )}

      {showBoard ? (
        <>
          <p className="muted">
            Ranked by how often each person has covered a call-out
            {data?.periods ? ` · learned from ${data.periods} schedule period${data.periods === 1 ? "" : "s"}` : ""}.
            The recommender uses this to balance the next ask.
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
              {people.length === 0 && !err && (
                <tr><td colSpan={6} className="muted">No history yet.</td></tr>
              )}
            </tbody>
          </table>
        </>
      ) : (
        <p className="muted">You can tune the scoring dial but not view the leaderboard.</p>
      )}
    </div>
  );
}
