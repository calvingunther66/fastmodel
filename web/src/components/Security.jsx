import React, { useState } from "react";
import { api } from "../api.js";

// Self-service two-factor auth (F2). Anyone can protect their own account;
// admins are strongly encouraged to.
export default function Security({ user, onChange }) {
  const enabled = !!user?.totp_enabled;
  const [enroll, setEnroll] = useState(null); // {secret, otpauth_uri}
  const [otp, setOtp] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function begin() {
    setErr(""); setMsg("");
    try { setEnroll(await api.begin2fa()); }
    catch (e) { setErr(e.message); }
  }

  async function confirm(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.enable2fa(otp.trim());
      setEnroll(null); setOtp(""); setMsg("Two-factor authentication is on.");
      onChange && onChange();
    } catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  }

  async function disable(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.disable2fa(pw);
      setPw(""); setMsg("Two-factor authentication is off.");
      onChange && onChange();
    } catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="card">
      <h2>Security</h2>
      <p className="muted">
        Two-factor authentication (TOTP) adds a one-time code from an
        authenticator app on top of your password.
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      <div className="sec-status">
        Two-factor authentication:{" "}
        <strong className={enabled ? "on-pill" : "off-pill"}>
          {enabled ? "ON" : "OFF"}
        </strong>
      </div>

      {!enabled && !enroll && (
        <button onClick={begin}>Set up two-factor authentication</button>
      )}

      {!enabled && enroll && (
        <form className="enroll" onSubmit={confirm}>
          <p>
            Add this account to your authenticator app — scan the QR (paste the
            link into a QR generator) or enter the secret by hand:
          </p>
          <div className="enroll-secret">
            <code>{enroll.secret}</code>
          </div>
          <details>
            <summary className="muted">otpauth link</summary>
            <code className="break">{enroll.otpauth_uri}</code>
          </details>
          <label>
            Enter the 6-digit code to confirm
            <input value={otp} onChange={(e) => setOtp(e.target.value)}
              inputMode="numeric" autoComplete="one-time-code" placeholder="123456" />
          </label>
          <div className="row gap">
            <button disabled={busy}>{busy ? "Confirming…" : "Turn on"}</button>
            <button type="button" className="ghost" onClick={() => setEnroll(null)}>Cancel</button>
          </div>
        </form>
      )}

      {enabled && (
        <form className="enroll" onSubmit={disable}>
          <p className="muted">Confirm your password to turn 2FA off.</p>
          <label>
            Current password
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          </label>
          <button className="danger" disabled={busy}>{busy ? "…" : "Turn off 2FA"}</button>
        </form>
      )}
    </div>
  );
}
