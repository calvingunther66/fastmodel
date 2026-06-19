// Tiny fetch wrapper. credentials:"include" carries the session cookie.
async function req(path, options = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  me: () => req("/api/me"),
  login: (username, password, otp) =>
    req("/api/login", { method: "POST", body: JSON.stringify({ username, password, otp }) }),
  logout: () => req("/api/logout", { method: "POST" }),
  // password reset (F3) — redeem an admin-issued one-time code
  resetPassword: (username, code, new_password) =>
    req("/api/reset-password", { method: "POST", body: JSON.stringify({ username, code, new_password }) }),
  // two-factor auth (F2)
  begin2fa: () => req("/api/me/2fa/begin", { method: "POST", body: "{}" }),
  enable2fa: (otp) => req("/api/me/2fa/enable", { method: "POST", body: JSON.stringify({ otp }) }),
  disable2fa: (password) => req("/api/me/2fa/disable", { method: "POST", body: JSON.stringify({ password }) }),
  schedule: () => req("/api/schedule"),
  people: () => req("/api/people"),
  reparse: (sheet) =>
    req("/api/schedule/reparse", { method: "POST", body: JSON.stringify({ sheet }) }),
  // user management (manage_users)
  users: () => req("/api/users"),
  createUser: (body) => req("/api/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (username, body) =>
    req(`/api/users/${encodeURIComponent(username)}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteUser: (username) =>
    req(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" }),
  resetCode: (username) =>
    req(`/api/users/${encodeURIComponent(username)}/reset-code`, { method: "POST", body: "{}" }),

  // self-service (member)
  availability: () => req("/api/availability"),
  myCallout: (date, shift_type) =>
    req("/api/me/callout", { method: "POST", body: JSON.stringify({ date, shift_type }) }),
  myCalloutClear: (date, shift_type) =>
    req("/api/me/callout/clear", { method: "POST", body: JSON.stringify({ date, shift_type }) }),
  myOffer: (date) => req("/api/me/offer", { method: "POST", body: JSON.stringify({ date }) }),
  myOfferRemove: (date) =>
    req("/api/me/offer/remove", { method: "POST", body: JSON.stringify({ date }) }),
  myContact: (contact) =>
    req("/api/me/contact", { method: "POST", body: JSON.stringify({ contact }) }),

  audit: (limit = 200) => req(`/api/audit?limit=${limit}`),
  coverageStats: () => req("/api/coverage/stats"),
  leaderboard: () => req("/api/coverage/leaderboard"),
  coverageSettings: () => req("/api/coverage/settings"),
  setCoverageSettings: (fairness_weight) =>
    req("/api/coverage/settings", { method: "POST", body: JSON.stringify({ fairness_weight }) }),

  callouts: () => req("/api/coverage/callouts"),
  sick: (name, date, shift_type) =>
    req("/api/coverage/sick", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),
  assign: (name, date, shift_type, covered_by) =>
    req("/api/coverage/assign", {
      method: "POST",
      body: JSON.stringify({ name, date, shift_type, covered_by }),
    }),
  assignCascade: (open, cascade) =>
    req("/api/coverage/assign-cascade", {
      method: "POST",
      body: JSON.stringify({
        name: open.name, date: open.date, shift_type: open.shift_type,
        mover: cascade.mover, backfill: cascade.backfill, from: cascade.from,
      }),
    }),
  clearCallout: (name, date, shift_type) =>
    req("/api/coverage/clear", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),
  unassignCover: (name, date, shift_type) =>
    req("/api/coverage/unassign", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),
  applyChain: (open, chain) =>
    req("/api/coverage/apply-chain", {
      method: "POST",
      body: JSON.stringify({
        name: open.name, date: open.date, shift_type: open.shift_type,
        steps: chain.steps, backfill: chain.backfill,
      }),
    }),
  // API tokens (manage_users)
  tokens: () => req("/api/tokens"),
  createToken: (name, capabilities) =>
    req("/api/tokens", { method: "POST", body: JSON.stringify({ name, capabilities }) }),
  revokeToken: (id) => req(`/api/tokens/${encodeURIComponent(id)}`, { method: "DELETE" }),
  // automation
  automationStatus: () => req("/api/automation/status"),
  automationSpreadsheets: () => req("/api/automation/spreadsheets"),
  automationIngestLatest: () =>
    req("/api/automation/ingest-latest", { method: "POST", body: "{}" }),

  roster: () => req("/api/roster"),
  setRoster: (staff) =>
    req("/api/roster", { method: "POST", body: JSON.stringify({ staff }) }),
  codes: () => req("/api/codes"),
  capabilities: () => req("/api/capabilities"),
  createSchedule: (body) =>
    req("/api/schedule/create", { method: "POST", body: JSON.stringify(body) }),

  // coverage gap forecaster (K2)
  forecast: () => req("/api/coverage/forecast"),

  // holiday registry (H3)
  holidays: () => req("/api/holidays"),
  addHoliday: (date, label) =>
    req("/api/holidays", { method: "POST", body: JSON.stringify({ date, label }) }),
  removeHoliday: (date) =>
    req(`/api/holidays/${encodeURIComponent(date)}`, { method: "DELETE" }),

  // vacation approvals (H1)
  vacations: () => req("/api/vacations"),
  decideVacation: (person, date, status) =>
    req("/api/vacations/decide", { method: "POST", body: JSON.stringify({ person, date, status }) }),

  // validator (A2/A3) + generator (C1) + templates (C3)
  issues: () => req("/api/schedule/issues"),
  generate: (start, end) =>
    req("/api/schedule/generate", { method: "POST", body: JSON.stringify({ start, end }) }),
  templates: () => req("/api/templates"),
  saveTemplate: (name, weekday_levels) =>
    req("/api/templates", { method: "POST", body: JSON.stringify({ name, weekday_levels }) }),
  deleteTemplate: (name) =>
    req(`/api/templates/${encodeURIComponent(name)}`, { method: "DELETE" }),

  // member preferences (B4)
  myPrefs: () => req("/api/me/prefs"),
  setMyPrefs: (prefs) =>
    req("/api/me/prefs", { method: "POST", body: JSON.stringify(prefs) }),

  // open shifts + claims (B1)
  openShifts: () => req("/api/open-shifts"),
  claim: (name, date, shift_type) =>
    req("/api/me/claim", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),
  unclaim: (name, date, shift_type) =>
    req("/api/me/claim/remove", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),
  approveClaim: (name, date, shift_type, claimer) =>
    req("/api/coverage/approve-claim", {
      method: "POST", body: JSON.stringify({ name, date, shift_type, claimer }) }),

  // what-if simulator (C2)
  simulate: (name, date, shift_type) =>
    req("/api/coverage/simulate", { method: "POST", body: JSON.stringify({ name, date, shift_type }) }),

  // shift swaps (B3)
  swaps: () => req("/api/swaps"),
  proposeSwap: (body) => req("/api/me/swap", { method: "POST", body: JSON.stringify(body) }),
  acceptSwap: (id) => req("/api/me/swap/accept", { method: "POST", body: JSON.stringify({ id }) }),
  decideSwap: (id, decision) =>
    req("/api/swaps/decide", { method: "POST", body: JSON.stringify({ id, decision }) }),

  async upload(file) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/schedule/upload", {
      method: "POST",
      credentials: "include",
      body: fd,
    });
    if (!res.ok) throw new Error((await res.json()).detail || "upload failed");
    return res.json();
  },
};
