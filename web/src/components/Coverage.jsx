import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { timeLabel } from "../utils.js";

// Trial feature: mark a shift "out sick", get ranked cover proposals, assign one.
export default function Coverage({ schedule, onChange }) {
  const people = (schedule?.people || []).filter((p) => p.name);
  const [name, setName] = useState("");
  const [proposal, setProposal] = useState(null);
  const [callouts, setCallouts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState(null);
  const [weight, setWeight] = useState(null);

  const person = people.find((p) => p.name === name);
  // Only real worked assignments make sense to call out.
  const workable = (person?.shifts || []).filter((s) => s.category === "location");

  function refreshCallouts() {
    api.callouts().then(setCallouts).catch(() => setCallouts([]));
  }
  useEffect(() => {
    refreshCallouts();
    api.coverageStats().then(setStats).catch(() => setStats(null));
    api.coverageSettings().then((s) => setWeight(s.fairness_weight)).catch(() => setWeight(null));
  }, [schedule]);

  const leaning = weight == null ? "" :
    weight <= 0.34 ? `leaning toward competence (${Math.round(weight * 100)}% fairness)`
    : weight >= 0.66 ? `leaning toward fairness (${Math.round(weight * 100)}% fairness)`
    : `balanced (${Math.round(weight * 100)}% fairness)`;

  const totalCovers = stats
    ? Object.values(stats.covers || {}).reduce((a, c) => a + (c.count || 0), 0)
    : 0;

  async function markSick(s) {
    setBusy(true);
    try {
      const p = await api.sick(name, s.date, s.shift_type);
      setProposal(p);
      refreshCallouts();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function assign(cand) {
    setBusy(true);
    try {
      await api.assign(proposal.open_shift.name, proposal.open_shift.date,
        proposal.open_shift.shift_type, cand);
      refreshCallouts();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function applyCascade(cascade) {
    setBusy(true);
    try {
      await api.assignCascade(proposal.open_shift, cascade);
      refreshCallouts();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function clear(co) {
    setBusy(true);
    try {
      await api.clearCallout(co.name, co.date, co.shift_type);
      if (proposal && proposal.open_shift.name === co.name &&
          proposal.open_shift.date === co.date &&
          proposal.open_shift.shift_type === co.shift_type) setProposal(null);
      refreshCallouts();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function unassign(co) {
    setBusy(true);
    try {
      await api.unassignCover(co.name, co.date, co.shift_type);
      refreshCallouts();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Call-outs & coverage <span className="trial">trial</span></h2>
      <p className="muted">
        Mark someone out sick for one shift; the system flags it open and proposes
        who could cover or be moved. Assigning a cover updates the grid and that
        person’s calendar feed.
      </p>
      {stats && (
        <p className="adaptive-note">
          🧠 Ranking adapts from history: learned from {stats.periods} schedule
          period{stats.periods === 1 ? "" : "s"} and {totalCovers} past cover
          {totalCovers === 1 ? "" : "s"}. The dial balances who knows the role
          against sharing the load.
          {leaning && <><br />Recommender dial: <strong>{leaning}</strong>.</>}
        </p>
      )}

      <label className="picker">
        Who is out:
        <select value={name} onChange={(e) => { setName(e.target.value); setProposal(null); }}>
          <option value="">— choose a person —</option>
          {people.map((p) => (
            <option key={p.name} value={p.name}>{p.name}</option>
          ))}
        </select>
      </label>

      {person && (
        <div className="shift-pick">
          {workable.length === 0 && <p className="muted">No worked shifts to call out.</p>}
          {workable.map((s, i) => (
            <button key={i} className="ghost" disabled={busy} onClick={() => markSick(s)}>
              Out sick: {s.date} · {s.code} ({s.shift_type}) — find coverage
            </button>
          ))}
        </div>
      )}

      {proposal && (
        <div className="proposal">
          <h3>
            Open: {proposal.open_shift.name}’s {proposal.open_shift.code}{" "}
            ({proposal.open_shift.shift_type}) on {proposal.open_shift.date}
            {proposal.open_shift.start &&
              ` · ${proposal.open_shift.start}–${proposal.open_shift.end}`}
          </h3>

          <h4>Free to cover</h4>
          <CandidateList rows={proposal.free_candidates} busy={busy} onAssign={assign} />

          <h4>Could be moved</h4>
          <CandidateList rows={proposal.move_candidates} busy={busy} onAssign={assign}
            empty="No qualified people are working that day to move." />

          <h4>Move + backfill (cascade)</h4>
          {(!proposal.cascades || proposal.cascades.length === 0) && (
            <p className="muted">No cascade chains found.</p>
          )}
          <ul className="cand-list">
            {(proposal.cascades || []).map((c, i) => (
              <li key={i}>
                <div className="cand-main">
                  <span className="cand-reasons">{c.summary}</span>
                  <span className="cand-contact">
                    backfill: {c.backfill_reasons.join("; ")}
                  </span>
                </div>
                <button disabled={busy} onClick={() => applyCascade(c)}>Apply</button>
              </li>
            ))}
          </ul>

          {proposal.unavailable_qualified?.length > 0 && (
            <>
              <h4>Qualified but off that day</h4>
              <ul className="cand-list muted-list">
                {proposal.unavailable_qualified.map((c, i) => (
                  <li key={i}>
                    <div className="cand-main">
                      <span className="cand-name">{c.name}</span>
                      <span className="cand-reasons">{c.reason}
                        {c.contact?.length > 0 ? ` · ${c.contact[0]}` : ""}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <h3>Active call-outs</h3>
      {callouts.length === 0 && <p className="muted">None right now.</p>}
      <ul className="callout-list">
        {callouts.map((co, i) => (
          <li key={i}>
            <span className="who">{co.name}</span>
            <span className="when">{co.date} · {co.shift_type}</span>
            <span className={co.covered_by ? "covered" : "open"}>
              {co.covered_by ? `covered by ${co.covered_by}` : "OPEN — needs coverage"}
            </span>
            {co.covered_by && (
              <button className="ghost small" disabled={busy} onClick={() => unassign(co)}
                title="Undo the assignment — reopens the shift">
                undo assign
              </button>
            )}
            <button className="ghost small" disabled={busy} onClick={() => clear(co)}>
              clear
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CandidateList({ rows, busy, onAssign, empty }) {
  if (!rows || rows.length === 0) return <p className="muted">{empty || "No candidates."}</p>;
  return (
    <ul className="cand-list">
      {rows.map((c, i) => (
        <li key={i}>
          <div className="cand-main">
            <span className="cand-name">{c.name}</span>
            {c.contact?.length > 0 && <span className="cand-contact">{c.contact[0]}</span>}
            {c.explanation && <span className="cand-why">{c.explanation}</span>}
            <span className="cand-reasons">{c.reasons.join("; ")}</span>
          </div>
          <button disabled={busy} onClick={() => onAssign(c.name)}>Assign</button>
        </li>
      ))}
    </ul>
  );
}
