import React, { useState } from "react";
import { api } from "../api.js";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("login"); // "login" | "reset"

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(username, password, needOtp ? otp : undefined);
      onLogin();
    } catch (err) {
      if (err.message === "otp_required") {
        setNeedOtp(true);
        setError("");
      } else {
        setError(err.message || "Login failed");
      }
    } finally {
      setBusy(false);
    }
  }

  if (mode === "reset") {
    return <ResetForm onBack={() => setMode("login")} />;
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>Schedule</h1>
        <p className="muted">Sign in to view the schedule.</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)}
            disabled={needOtp} autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} disabled={needOtp}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {needOtp && (
          <label>
            Authentication code
            <input value={otp} onChange={(e) => setOtp(e.target.value)}
              inputMode="numeric" autoComplete="one-time-code" autoFocus
              placeholder="6-digit code" />
            <span className="muted small">From your authenticator app.</span>
          </label>
        )}
        {error && <div className="error" role="alert">{error}</div>}
        <button disabled={busy}>{busy ? "Signing in…" : needOtp ? "Verify" : "Sign in"}</button>
        <button type="button" className="link-btn" onClick={() => setMode("reset")}>
          Have a reset code?
        </button>
      </form>
    </div>
  );
}

function ResetForm({ onBack }) {
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.resetPassword(username, code.trim(), pw);
      setDone(true);
    } catch (err) {
      setError(err.message || "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>Reset password</h1>
        {done ? (
          <>
            <p className="muted">Password updated. You can sign in now.</p>
            <button type="button" onClick={onBack}>Back to sign in</button>
          </>
        ) : (
          <>
            <p className="muted">Enter the one-time code an admin gave you.</p>
            <label>
              Username
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
            </label>
            <label>
              Reset code
              <input value={code} onChange={(e) => setCode(e.target.value)}
                placeholder="e.g. A1B2C3D4" />
            </label>
            <label>
              New password
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </label>
            {error && <div className="error" role="alert">{error}</div>}
            <button disabled={busy}>{busy ? "Saving…" : "Set new password"}</button>
            <button type="button" className="link-btn" onClick={onBack}>Cancel</button>
          </>
        )}
      </form>
    </div>
  );
}
