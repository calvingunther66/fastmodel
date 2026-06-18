import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const CAPS = ["upload", "manage_coverage", "manage_users", "view_leaderboard", "tune_scoring", "automate"];
const TOKEN_CAPS = ["automate", "upload"];

export default function Users({ schedule }) {
  const [users, setUsers] = useState([]);
  const [names, setNames] = useState([]);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    username: "", password: "", role: "member", person: "", capabilities: [],
  });

  function refresh() {
    api.users().then(setUsers).catch((e) => setErr(e.message));
  }
  useEffect(() => {
    refresh();
    api.people().then((p) => setNames(p.map((x) => x.name))).catch(() => setNames([]));
  }, []);

  function toggleCap(list, c) {
    return list.includes(c) ? list.filter((x) => x !== c) : [...list, c];
  }

  async function create(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.createUser({
        ...form, person: form.person || null,
      });
      setForm({ username: "", password: "", role: "member", person: "", capabilities: [] });
      refresh();
    } catch (e2) { setErr(e2.message); }
  }

  async function patch(u, body) {
    setErr("");
    try { await api.updateUser(u.username, body); refresh(); }
    catch (e2) { setErr(e2.message); }
  }

  async function resetPw(u) {
    const pw = prompt(`New password for ${u.username}:`);
    if (pw) patch(u, { password: pw });
  }

  async function remove(u) {
    if (!confirm(`Delete account ${u.username}?`)) return;
    setErr("");
    try { await api.deleteUser(u.username); refresh(); }
    catch (e2) { setErr(e2.message); }
  }

  return (
    <div className="card">
      <h2>Accounts</h2>
      <p className="muted">
        Create an account per person and link it to their schedule name. Grant
        members extra capabilities to delegate admin powers.
      </p>
      {err && <div className="error">{err}</div>}

      <form className="user-form" onSubmit={create}>
        <input placeholder="username" value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        <input placeholder="password" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="member">member</option>
          <option value="admin">admin</option>
        </select>
        <select value={form.person} onChange={(e) => setForm({ ...form, person: e.target.value })}>
          <option value="">— link to person —</option>
          {names.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <div className="caps">
          {CAPS.map((c) => (
            <label key={c} className={form.role === "admin" ? "muted" : ""}>
              <input type="checkbox" disabled={form.role === "admin"}
                checked={form.role === "admin" || form.capabilities.includes(c)}
                onChange={() => setForm({ ...form, capabilities: toggleCap(form.capabilities, c) })} />
              {c}
            </label>
          ))}
        </div>
        <button>Create account</button>
      </form>

      <table className="users-table">
        <thead>
          <tr><th>User</th><th>Role</th><th>Person</th><th>Capabilities</th><th></th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.username}>
              <td>{u.username}{u.protected && <span className="role-tag">env</span>}</td>
              <td>
                <select value={u.role} disabled={u.protected}
                  onChange={(e) => patch(u, { role: e.target.value })}>
                  <option value="member">member</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td>
                <select value={u.person || ""}
                  onChange={(e) => patch(u, { person: e.target.value || null })}>
                  <option value="">—</option>
                  {names.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </td>
              <td className="caps">
                {u.role === "admin" ? <span className="muted">all</span> : CAPS.map((c) => (
                  <label key={c}>
                    <input type="checkbox" checked={u.capabilities.includes(c)}
                      onChange={() => patch(u, {
                        capabilities: u.capabilities.includes(c)
                          ? u.capabilities.filter((x) => x !== c) : [...u.capabilities, c],
                      })} />
                    {c}
                  </label>
                ))}
              </td>
              <td className="user-actions">
                <button className="ghost small" onClick={() => resetPw(u)}>password</button>
                {!u.protected &&
                  <button className="ghost small danger" onClick={() => remove(u)}>delete</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ApiTokens />
    </div>
  );
}

function ApiTokens() {
  const [tokens, setTokens] = useState([]);
  const [name, setName] = useState("");
  const [caps, setCaps] = useState(["automate"]);
  const [fresh, setFresh] = useState(null);
  const [err, setErr] = useState("");

  function refresh() { api.tokens().then(setTokens).catch((e) => setErr(e.message)); }
  useEffect(() => { refresh(); }, []);

  async function create(e) {
    e.preventDefault();
    setErr(""); setFresh(null);
    try {
      const r = await api.createToken(name || "agent", caps);
      setFresh(r.token); setName(""); refresh();
    } catch (e2) { setErr(e2.message); }
  }
  async function revoke(id) {
    if (!confirm("Revoke this token? Any agent using it loses access.")) return;
    await api.revokeToken(id); refresh();
  }

  return (
    <div className="tokens">
      <h3>Automation API tokens</h3>
      <p className="muted">
        Bearer keys for headless agents (the Claude MCP routine). Scoped, revocable,
        and audit-logged. The secret is shown once — copy it now.
      </p>
      {err && <div className="error">{err}</div>}
      {fresh && (
        <div className="token-fresh">
          New token (copy now, it won’t be shown again):
          <code>{fresh}</code>
        </div>
      )}
      <form className="user-form" onSubmit={create}>
        <input placeholder="token name (e.g. claude-agent)" value={name}
          onChange={(e) => setName(e.target.value)} />
        <div className="caps">
          {TOKEN_CAPS.map((c) => (
            <label key={c}>
              <input type="checkbox" checked={caps.includes(c)}
                onChange={() => setCaps(caps.includes(c) ? caps.filter((x) => x !== c) : [...caps, c])} />
              {c}
            </label>
          ))}
        </div>
        <button>Mint token</button>
      </form>
      <ul className="callout-list">
        {tokens.map((t) => (
          <li key={t.id}>
            <span className="who">{t.name}</span>
            <span className="when">{(t.capabilities || []).join(", ")}</span>
            <span className="muted">{t.last_used ? `used ${new Date(t.last_used).toLocaleString()}` : "never used"}</span>
            <button className="ghost small danger" onClick={() => revoke(t.id)}>revoke</button>
          </li>
        ))}
        {tokens.length === 0 && <li className="muted">No tokens.</li>}
      </ul>
    </div>
  );
}
