import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Login from "./components/Login.jsx";
import ScheduleGrid from "./components/ScheduleGrid.jsx";
import MyCalendar from "./components/MyCalendar.jsx";
import MyAvailability from "./components/MyAvailability.jsx";
import Coverage from "./components/Coverage.jsx";
import Admin from "./components/Admin.jsx";
import Create from "./components/Create.jsx";
import Users from "./components/Users.jsx";
import Insights from "./components/Insights.jsx";
import Activity from "./components/Activity.jsx";
import OpenShifts from "./components/OpenShifts.jsx";
import Roster from "./components/Roster.jsx";
import Security from "./components/Security.jsx";
import Vacations from "./components/Vacations.jsx";
import Holidays from "./components/Holidays.jsx";
import Forecast from "./components/Forecast.jsx";
import Backup from "./components/Backup.jsx";
import Ops from "./components/Ops.jsx";
import MyChanges from "./components/MyChanges.jsx";

// Theme: "light" | "dark" | null (follow OS). Persisted in localStorage and
// reflected on <html data-theme> so the CSS variables switch.
function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme"));
  useEffect(() => {
    const root = document.documentElement;
    if (theme) root.setAttribute("data-theme", theme);
    else root.removeAttribute("data-theme");
    if (theme) localStorage.setItem("theme", theme);
    else localStorage.removeItem("theme");
  }, [theme]);
  const isDark = theme === "dark"
    || (!theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  return [isDark, () => setTheme(isDark ? "light" : "dark")];
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authed, setAuthed] = useState(null);
  const [tab, setTab] = useState("schedule");
  const [schedule, setSchedule] = useState(null);
  const [isDark, toggleTheme] = useTheme();

  function loadMe() {
    return api.me()
      .then((r) => { setAuthed(r.authenticated); setUser(r.user || null); })
      .catch(() => { setAuthed(false); setUser(null); });
  }
  useEffect(() => { loadMe(); }, []);

  function loadSchedule() {
    api.schedule().then(setSchedule).catch(() => setSchedule(null));
  }
  useEffect(() => { if (authed) loadSchedule(); }, [authed]);

  if (authed === null) return <div className="center muted">Loading…</div>;
  if (!authed) return <Login onLogin={() => loadMe()} />;

  const role = user?.role;
  const caps = user?.capabilities || [];
  const can = (c) => role === "admin" || caps.includes(c);
  const empty = !schedule || schedule.empty;

  const tabs = [
    { id: "schedule", label: "Schedule", show: true },
    { id: "calendar", label: "My calendar", show: true },
    { id: "availability", label: "My availability", show: !!user?.person },
    { id: "openshifts", label: "Open shifts",
      show: !!user?.person || can("manage_coverage") || can("manage_swaps") },
    { id: "coverage", label: "Coverage", show: can("manage_coverage") },
    { id: "admin", label: "Upload", show: can("upload") },
    { id: "create", label: "Create", show: can("upload") || can("generate_schedule") },
    { id: "roster", label: "Roster", show: can("manage_roster") },
    { id: "users", label: "Users", show: can("manage_users") },
    { id: "insights", label: "Insights", show: can("view_leaderboard") || can("tune_scoring") },
    { id: "activity", label: "Activity", show: can("manage_users") || can("manage_coverage") },
    { id: "security", label: "Security", show: true },
  ].filter((t) => t.show);

  const activeTab = tabs.some((t) => t.id === tab) ? tab : "schedule";

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>
      <header>
        <h1>Schedule</h1>
        <nav aria-label="Primary">
          {tabs.map((t) => (
            <button key={t.id} className={activeTab === t.id ? "on" : ""}
              aria-current={activeTab === t.id ? "page" : undefined}
              onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
          <span className="who-am-i">
            {user?.username}{user?.person ? ` · ${user.person}` : ""}
            <span className="role-tag">{role}</span>
          </span>
          <button className="theme-toggle" onClick={toggleTheme}
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            title={isDark ? "Light mode" : "Dark mode"}>{isDark ? "☀" : "☾"}</button>
          <button className="logout" onClick={() => api.logout().then(loadMe)}>Sign out</button>
        </nav>
      </header>

      {schedule?.parsed_sheet && (
        <div className="subbar">
          <strong>{schedule.parsed_sheet}</strong>
          {schedule.date_range && (
            <span className="muted"> · {schedule.date_range.start} → {schedule.date_range.end}</span>
          )}
          {can("export") && (
            <a className="export-link" href="/api/export/schedule.csv">⤓ CSV</a>
          )}
          <button className="export-link print-btn" onClick={() => window.print()}>⎙ Print</button>
        </div>
      )}

      <main id="main">
        {empty && !["admin", "create", "users"].includes(activeTab) && (
          <p className="muted">
            No schedule loaded yet{can("upload") ? " — go to “Upload” or “Create”." : "."}
          </p>
        )}
        {activeTab === "schedule" && !empty && <ScheduleGrid schedule={schedule} user={user} />}
        {activeTab === "calendar" && !empty && <MyCalendar schedule={schedule} user={user} />}
        {activeTab === "availability" && !empty && <>
          <MyChanges person={user?.person} />
          <MyAvailability schedule={schedule} user={user} onChange={loadSchedule} />
        </>}
        {activeTab === "openshifts" &&
          <OpenShifts user={user} can={can} onChange={loadSchedule} />}
        {activeTab === "coverage" && !empty && <>
          <Coverage schedule={schedule} onChange={loadSchedule} />
          <Forecast />
          <Vacations onChange={loadSchedule} />
          <Holidays onChange={loadSchedule} />
        </>}
        {activeTab === "admin" && <Admin schedule={schedule} onChange={loadSchedule} />}
        {activeTab === "create" && <Create onChange={loadSchedule} can={can} />}
        {activeTab === "roster" && <Roster />}
        {activeTab === "users" && <><Users schedule={schedule} /><Ops /><Backup /></>}
        {activeTab === "insights" && <Insights can={can} />}
        {activeTab === "activity" && <Activity />}
        {activeTab === "security" && <Security user={user} onChange={loadMe} />}
      </main>
    </div>
  );
}
