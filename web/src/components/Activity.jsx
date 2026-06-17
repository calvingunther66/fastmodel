import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const LABELS = {
  login: "signed in",
  upload_schedule: "uploaded a schedule",
  mark_sick: "marked out sick",
  self_callout: "called out (self)",
  assign_cover: "assigned a cover",
  assign_cascade: "applied a cascade",
  clear_callout: "cleared a call-out",
  offer_cover: "offered to cover",
  edit_contact: "edited contact info",
  user_create: "created an account",
  user_update: "updated an account",
  user_delete: "deleted an account",
};

function describe(e) {
  const d = e.details || {};
  switch (e.action) {
    case "upload_schedule": return `“${d.sheet}”`;
    case "mark_sick": return `${d.name} · ${d.date} ${d.shift}`;
    case "self_callout": return `${d.person} · ${d.date} ${d.shift}`;
    case "assign_cover": return `${d.covered_by} covers ${d.name} · ${d.date} ${d.shift}`;
    case "assign_cascade": return `${d.mover}→${d.name}, backfill ${d.backfill} · ${d.date}`;
    case "clear_callout": return `${d.name} · ${d.date} ${d.shift}`;
    case "offer_cover": return `${d.person} · ${d.date}`;
    case "edit_contact": return d.person || "";
    case "user_create": return `${d.username} (${d.role})`;
    case "user_update": return `${d.username}${d.password_reset ? " · password reset" : ""}`;
    case "user_delete": return d.username;
    default: return "";
  }
}

export default function Activity() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.audit(300).then(setRows).catch((e) => setErr(e.message));
  }, []);

  return (
    <div className="card">
      <h2>Activity log</h2>
      <p className="muted">Every account/coverage action, newest first.</p>
      {err && <div className="error">{err}</div>}
      <ul className="audit-list">
        {rows.map((e, i) => (
          <li key={i}>
            <span className="a-ts">{new Date(e.ts).toLocaleString()}</span>
            <span className="a-actor">{e.actor}</span>
            <span className="a-act">{LABELS[e.action] || e.action}</span>
            <span className="a-det">{describe(e)}</span>
          </li>
        ))}
        {rows.length === 0 && !err && <li className="muted">No activity yet.</li>}
      </ul>
    </div>
  );
}
