import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Login from "./components/Login.jsx";
import ScheduleGrid from "./components/ScheduleGrid.jsx";
import MyCalendar from "./components/MyCalendar.jsx";
import MyAvailability from "./components/MyAvailability.jsx";
import Coverage from "./components/Coverage.jsx";
import Admin from "./components/Admin.jsx";
import Users from "./components/Users.jsx";
import Insights from "./components/Insights.jsx";
import Activity from "./components/Activity.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [authed, setAuthed] = useState(null);
  const [tab, setTab] = useState("schedule");
  const [schedule, setSchedule] = useState(null);

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
    { id: "coverage", label: "Coverage", show: can("manage_coverage") },
    { id: "admin", label: "Upload", show: can("upload") },
    { id: "users", label: "Users", show: can("manage_users") },
    { id: "insights", label: "Insights", show: can("view_leaderboard") || can("tune_scoring") },
    { id: "activity", label: "Activity", show: can("manage_users") || can("manage_coverage") },
  ].filter((t) => t.show);

  const activeTab = tabs.some((t) => t.id === tab) ? tab : "schedule";

  return (
    <div className="app">
      <header>
        <h1>Schedule</h1>
        <nav>
          {tabs.map((t) => (
            <button key={t.id} className={activeTab === t.id ? "on" : ""}
              onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
          <span className="who-am-i">
            {user?.username}{user?.person ? ` · ${user.person}` : ""}
            <span className="role-tag">{role}</span>
          </span>
          <button className="logout" onClick={() => api.logout().then(loadMe)}>Sign out</button>
        </nav>
      </header>

      {schedule?.parsed_sheet && (
        <div className="subbar">
          <strong>{schedule.parsed_sheet}</strong>
          {schedule.date_range && (
            <span className="muted"> · {schedule.date_range.start} → {schedule.date_range.end}</span>
          )}
        </div>
      )}

      <main>
        {empty && activeTab !== "admin" && activeTab !== "users" && (
          <p className="muted">No schedule loaded yet{can("upload") ? " — go to “Upload”." : "."}</p>
        )}
        {activeTab === "schedule" && !empty && <ScheduleGrid schedule={schedule} />}
        {activeTab === "calendar" && !empty && <MyCalendar schedule={schedule} user={user} />}
        {activeTab === "availability" && !empty &&
          <MyAvailability schedule={schedule} user={user} onChange={loadSchedule} />}
        {activeTab === "coverage" && !empty &&
          <Coverage schedule={schedule} onChange={loadSchedule} />}
        {activeTab === "admin" && <Admin schedule={schedule} onChange={loadSchedule} />}
        {activeTab === "users" && <Users schedule={schedule} />}
        {activeTab === "insights" && <Insights can={can} />}
        {activeTab === "activity" && <Activity />}
      </main>
    </div>
  );
}
