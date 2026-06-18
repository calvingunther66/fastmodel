import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Staff roster editor (A1). Drives qualification + no-nights rules in the coverage
// engine, validator and generator. Edit clinics (comma-separated codes), employment,
// seniority, and works-nights per person. Requires the manage_roster capability.
export default function Roster() {
  const [staff, setStaff] = useState([]);
  const [placeholder, setPlaceholder] = useState(false);
  const [codes, setCodes] = useState([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.roster().then((r) => { setStaff(r.staff || []); setPlaceholder(r.placeholder); });
    api.codes().then((c) => setCodes(c.clinics || [])).catch(() => {});
  }, []);

  function update(i, field, value) {
    setStaff((s) => s.map((row, j) => (j === i ? { ...row, [field]: value } : row)));
  }
  function addRow() {
    setStaff((s) => [...s, { name: "", clinics: [], employment: "career",
      seniority: false, works_nights: true }]);
  }
  function removeRow(i) { setStaff((s) => s.filter((_, j) => j !== i)); }

  function save() {
    setMsg(""); setErr("");
    const clean = staff
      .filter((r) => r.name && r.name.trim())
      .map((r) => ({
        ...r,
        clinics: Array.isArray(r.clinics) ? r.clinics
          : String(r.clinics || "").split(/[,\s]+/).filter(Boolean),
      }));
    api.setRoster(clean)
      .then((r) => { setStaff(r.staff); setPlaceholder(r.placeholder);
        setMsg(`Saved ${r.staff.length} staff.`); })
      .catch((e) => setErr(e.message));
  }

  return (
    <div className="roster-editor">
      <h2>Staff roster</h2>
      {placeholder && <p className="warn">Placeholder data — replace with the real roster.</p>}
      <p className="muted">Known clinic codes: {codes.join(", ") || "—"}. Clinics gate
        who the engine will recommend; un-tick “nights” for no-nights staff.</p>
      <table className="grid-table">
        <thead>
          <tr><th>Name</th><th>Clinics</th><th>Employment</th><th>Seniority</th>
            <th>Nights</th><th></th></tr>
        </thead>
        <tbody>
          {staff.map((r, i) => (
            <tr key={i}>
              <td><input value={r.name || ""} onChange={(e) => update(i, "name", e.target.value)} /></td>
              <td>
                <input style={{ width: "12rem" }}
                  value={Array.isArray(r.clinics) ? r.clinics.join(", ") : r.clinics || ""}
                  onChange={(e) => update(i, "clinics", e.target.value.split(/[,\s]+/).filter(Boolean))}
                  placeholder="BC, HC, CV" />
              </td>
              <td>
                <select value={r.employment || "career"}
                  onChange={(e) => update(i, "employment", e.target.value)}>
                  <option value="career">career</option>
                  <option value="per_diem">per-diem</option>
                </select>
              </td>
              <td><input type="checkbox" checked={!!r.seniority}
                onChange={(e) => update(i, "seniority", e.target.checked)} /></td>
              <td><input type="checkbox" checked={r.works_nights !== false}
                onChange={(e) => update(i, "works_nights", e.target.checked)} /></td>
              <td><button className="ghost" onClick={() => removeRow(i)}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row gap">
        <button onClick={addRow}>+ Add person</button>
        <button className="primary" onClick={save}>Save roster</button>
        {msg && <span className="ok">{msg}</span>}
        {err && <span className="error">{err}</span>}
      </div>
    </div>
  );
}
