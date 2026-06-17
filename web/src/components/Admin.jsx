import React, { useRef, useState } from "react";
import { api } from "../api.js";

export default function Admin({ schedule, onChange }) {
  const fileRef = useRef();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const sheets = schedule?.available_sheets || [];

  async function upload() {
    const file = fileRef.current.files[0];
    if (!file) return;
    setBusy(true);
    setStatus("");
    try {
      const r = await api.upload(file);
      setStatus(`Loaded “${r.parsed_sheet}” — ${r.people} people.`);
      onChange();
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      setBusy(false);
    }
  }

  async function switchSheet(sheet) {
    if (!sheet) return;
    setBusy(true);
    try {
      await api.reparse(sheet);
      setStatus(`Now showing “${sheet}”.`);
      onChange();
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Upload a new schedule</h2>
      <p className="muted">
        Upload the latest <code>.xlsx</code>. Existing calendar links keep working —
        they’ll just show the new schedule.
      </p>
      <div className="row">
        <input ref={fileRef} type="file" accept=".xlsx,.xlsm" />
        <button onClick={upload} disabled={busy}>
          {busy ? "Working…" : "Upload"}
        </button>
      </div>

      {sheets.length > 1 && (
        <label className="picker">
          Active sheet:
          <select
            value={schedule?.parsed_sheet || ""}
            onChange={(e) => switchSheet(e.target.value)}
          >
            {sheets.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}

      {status && <div className="status">{status}</div>}
    </div>
  );
}
