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
  login: (username, password) =>
    req("/api/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => req("/api/logout", { method: "POST" }),
  schedule: () => req("/api/schedule"),
  people: () => req("/api/people"),
  reparse: (sheet) =>
    req("/api/schedule/reparse", { method: "POST", body: JSON.stringify({ sheet }) }),
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
