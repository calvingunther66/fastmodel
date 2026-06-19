import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// Admin ops dashboard (L2): config + data + health at a glance.
function kb(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function Ops() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [kiosk, setKiosk] = useState(null);
  useEffect(() => {
    api.ops().then(setD).catch((e) => setErr(e.message));
    api.kioskToken().then(setKiosk).catch(() => {});
  }, []);

  function rotateKiosk() {
    if (!confirm("Rotate the kiosk link? The old URL stops working.")) return;
    api.rotateKiosk().then(setKiosk).catch((e) => setErr(e.message));
  }

  if (err) return <div className="card"><div className="error" role="alert">{err}</div></div>;
  if (!d) return null;

  const c = d.config;
  return (
    <div className="card ops">
      <h2>System <span className="muted">v{d.version}</span></h2>

      {c.using_default_password && (
        <div className="error" role="alert">
          ⚠ Still using the default admin password — set APP_PASSWORD.
        </div>
      )}

      <div className="ops-grid">
        <div>
          <h3>Configuration</h3>
          <dl className="ops-dl">
            <dt>Timezone</dt><dd>{c.timezone}</dd>
            <dt>Public base URL</dt><dd>{c.public_base_url || <span className="muted">from request</span>}</dd>
            <dt>HTTPS-only cookie</dt><dd>{String(c.session_https_only)}</dd>
            <dt>Auto-ingest</dt><dd>{c.auto_ingest}</dd>
            <dt>Login lockout</dt><dd>{c.login_max_attempts} tries / {c.login_lockout_seconds}s</dd>
            <dt>Data dir</dt><dd className="break">{c.data_dir}</dd>
          </dl>
        </div>
        <div>
          <h3>State</h3>
          <dl className="ops-dl">
            <dt>Active sheet</dt><dd>{d.schedule.active_sheet || <span className="muted">none</span>}</dd>
            <dt>Uploaded</dt><dd>{d.schedule.uploaded_at ? new Date(d.schedule.uploaded_at).toLocaleString() : "—"}</dd>
            <dt>People</dt><dd>{d.schedule.people}</dd>
            <dt>Accounts</dt><dd>{d.accounts.total} ({d.accounts.admins} admin, {d.accounts.with_2fa} with 2FA)</dd>
            <dt>API tokens</dt><dd>{d.tokens}</dd>
            <dt>Data size</dt><dd>{kb(d.data.total_bytes)}</dd>
          </dl>
        </div>
      </div>

      {kiosk && (
        <div className="kiosk-info">
          <h3>Kiosk wall display</h3>
          <p className="muted">
            A no-login, auto-refreshing “who’s on today” board for a unit screen.
            Anyone with the link can view it — rotate it to revoke.
          </p>
          <div className="row gap">
            <a className="button-link" href={kiosk.url} target="_blank" rel="noreferrer">Open display</a>
            <input readOnly value={kiosk.url} onFocus={(e) => e.target.select()} style={{ flex: 1, minWidth: 220 }} />
            <button className="ghost" onClick={rotateKiosk}>Rotate link</button>
          </div>
        </div>
      )}

      <h3>Largest data files</h3>
      <ul className="callout-list">
        {d.data.files.slice(0, 8).map((f) => (
          <li key={f.name}>
            <span className="who">{f.name}</span>
            <span className="muted">{kb(f.bytes)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
