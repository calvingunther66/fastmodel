import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { dateRange, dayLabel } from "../utils.js";

// Schedule-creation workflow (placeholder roster for now). Builds the same
// schedule shape the rest of the app consumes, decoding codes -> times server-side.
const LEVELS = [
  { id: "day", label: "Day", cls: "day" },
  { id: "mid", label: "Mid", cls: "midshift" },
  { id: "night", label: "Night", cls: "night" },
];

export default function Create({ onChange, can }) {
  const [staff, setStaff] = useState([]);
  const [placeholder, setPlaceholder] = useState(false);
  const [codes, setCodes] = useState({ locations: {}, statuses: {} });
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [level, setLevel] = useState("day");
  const [assign, setAssign] = useState({}); // {name:{date:{level:code}}}
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.roster().then((r) => { setStaff(r.staff); setPlaceholder(r.placeholder); }).catch(() => {});
    api.codes().then(setCodes).catch(() => {});
  }, []);

  const dates = useMemo(() => dateRange(start, end), [start, end]);
  const options = useMemo(() => [
    ...Object.keys(codes.locations || {}),
    ...Object.keys(codes.statuses || {}),
  ], [codes]);

  function setCell(name, date, code) {
    setAssign((a) => {
      const next = { ...a, [name]: { ...(a[name] || {}) } };
      next[name][date] = { ...(next[name][date] || {}) };
      if (code) next[name][date][level] = code;
      else delete next[name][date][level];
      return next;
    });
  }

  async function create() {
    if (!title || !start || !end) { setStatus("Title and dates are required."); return; }
    try {
      const r = await api.createSchedule({ title, start, end, assignments: assign });
      setStatus(`Created “${r.title}” for ${r.people} people. It is now the active schedule.`);
      onChange?.();
    } catch (e) { setStatus("Error: " + e.message); }
  }

  // C1: auto-draft a fairness-aware schedule from the roster, loaded into the grid
  // for editing (nothing is saved until you press “Create schedule”).
  async function draft() {
    if (!start || !end) { setStatus("Pick a start and end date first."); return; }
    try {
      const d = await api.generate(start, end);
      setAssign(d.assignments || {});
      const r = d.report || {};
      const gaps = (r.unfilled || []).length;
      setStatus(`Drafted ${r.assigned} assignments for ${r.people} people over ${r.days} days`
        + (gaps ? `, ${gaps} slot(s) left unfilled — review & edit below.` : ". Review & edit, then Create."));
    } catch (e) { setStatus("Error: " + e.message); }
  }

  return (
    <div className="card">
      <h2>Create a schedule <span className="trial">preview</span></h2>
      {placeholder && (
        <p className="adaptive-note">
          Using <strong>placeholder staff</strong>. Edit the real roster (clinics
          per person, career/per-diem, seniority, no-nights) in the <strong>Roster</strong>
          tab and it powers generation, qualification and validation here.
        </p>
      )}

      <div className="create-head">
        <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Aug 1 – Aug 14" /></label>
        <label>Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>

      <div className="level-pick">
        Editing level:
        {LEVELS.map((l) => (
          <button key={l.id} className={`ghost ${level === l.id ? "on" : ""}`}
            onClick={() => setLevel(l.id)}>{l.label}</button>
        ))}
        <span className="muted">— pick a code in a cell to set the {level} shift</span>
      </div>

      {dates.length === 0 ? (
        <p className="muted">Pick a start and end date to lay out the grid.</p>
      ) : (
        <div className="grid-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th className="sticky name-col">Staff</th>
                {dates.map((d) => {
                  const { dom, dow, weekend } = dayLabel(d);
                  return <th key={d} className={weekend ? "weekend" : ""}>
                    <div className="dom">{dom}</div><div className="dow">{dow}</div></th>;
                })}
              </tr>
            </thead>
            <tbody>
              {staff.map((p) => (
                <tr key={p.name}>
                  <td className="sticky name-col">
                    <div className="staff-name">{p.name}</div>
                    <div className="staff-tags">
                      <span className="tag">{p.employment === "per_diem" ? "per-diem" : "career"}</span>
                      {p.seniority && <span className="tag">senior</span>}
                      {!p.works_nights && <span className="tag warn">no nights</span>}
                      <span className="tag muted-tag">{p.clinics.join(" ")}</span>
                    </div>
                  </td>
                  {dates.map((d) => {
                    const cell = (assign[p.name] || {})[d] || {};
                    const allowed = level === "night" ? p.works_nights : true;
                    return (
                      <td key={d} className={!allowed ? "cell-block" : ""}>
                        <div className="cell-codes">
                          {LEVELS.map((l) => cell[l.id] && (
                            <span key={l.id} className={`shift ${l.cls}`}>{cell[l.id]}</span>
                          ))}
                        </div>
                        <select className="cell-select" value={cell[level] || ""}
                          disabled={!allowed}
                          onChange={(e) => setCell(p.name, d, e.target.value)}>
                          <option value="">·</option>
                          {options.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="row" style={{ marginTop: 12 }}>
        {(can?.("generate_schedule")) && (
          <button className="primary" onClick={draft} disabled={!start || !end}>
            ✨ Generate draft
          </button>
        )}
        <button onClick={create}>Create schedule</button>
        {status && <span className="status">{status}</span>}
      </div>
    </div>
  );
}
