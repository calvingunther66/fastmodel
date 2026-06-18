import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function Admin({ schedule, onChange }) {
  const fileRef = useRef();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [auto, setAuto] = useState(null);
  const sheets = schedule?.available_sheets || [];

  useEffect(() => {
    api.automationStatus().then(setAuto).catch(() => setAuto(null));
  }, [schedule]);

  async function ingestLatest() {
    setBusy(true); setStatus("");
    try {
      const r = await api.automationIngestLatest();
      setStatus(`Automation: ${r.status}${r.file ? ` — ${r.file}` : ""}${r.period ? ` (${r.period})` : ""}.`);
      api.automationStatus().then(setAuto).catch(() => {});
      onChange();
    } catch (e) { setStatus("Error: " + e.message); }
    finally { setBusy(false); }
  }

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

      {auto && (
        <div className="auto-panel">
          <h3>Autonomous ingestion</h3>
          <p className="muted">
            Drop/sync your Excel files into the inbox and the latest is ingested
            (idempotently). An agent can do this on a schedule via the MCP endpoint.
          </p>
          <ul className="auto-stats">
            <li><span>Inbox</span><code>{auto.inbox}</code></li>
            <li><span>Spreadsheets waiting</span><strong>{auto.spreadsheets}</strong></li>
            <li><span>Periods ingested</span><strong>{(auto.periods_ingested || []).length}</strong></li>
            {auto.last && <li><span>Last run</span>
              <span>{auto.last.status} · {auto.last.file} · {new Date(auto.last.at).toLocaleString()}</span></li>}
          </ul>
          <button className="ghost" disabled={busy} onClick={ingestLatest}>
            Ingest latest now
          </button>
        </div>
      )}
    </div>
  );
}
