import React, { useRef, useState } from "react";
import { api } from "../api.js";

// Backup & restore the whole data directory (L1). Admin-only; handy before the
// Raspberry Pi hand-off or any risky change.
export default function Backup() {
  const fileRef = useRef(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function restore(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm(`Restore from ${file.name}? This overwrites current data — ` +
                 `download a backup first if unsure.`)) {
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api.restore(file);
      setMsg(`Restored ${r.restored} files. ${r.note || ""}`);
    } catch (e2) { setErr(e2.message); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  return (
    <div className="card backup">
      <h2>Backup &amp; restore</h2>
      <p className="muted">
        Download a full snapshot of all app data (accounts, schedule, tokens,
        history, settings), or restore one. Keep a backup before upgrades or the
        Pi hand-off.
      </p>
      {err && <div className="error" role="alert">{err}</div>}
      {msg && <div className="ok-banner" role="status">{msg}</div>}
      <div className="row gap">
        <a className="button-link" href="/api/backup">⤓ Download backup</a>
        <button className="ghost" disabled={busy}
          onClick={() => fileRef.current?.click()}>
          {busy ? "Restoring…" : "⤒ Restore from backup"}
        </button>
        <input ref={fileRef} type="file" accept=".zip" style={{ display: "none" }}
          onChange={restore} />
      </div>
    </div>
  );
}
