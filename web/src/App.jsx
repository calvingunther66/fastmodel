import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Login from "./components/Login.jsx";
import ScheduleGrid from "./components/ScheduleGrid.jsx";
import MyCalendar from "./components/MyCalendar.jsx";
import Admin from "./components/Admin.jsx";

export default function App() {
  const [authed, setAuthed] = useState(null);
  const [tab, setTab] = useState("schedule");
  const [schedule, setSchedule] = useState(null);

  useEffect(() => {
    api.me().then((r) => setAuthed(r.authenticated)).catch(() => setAuthed(false));
  }, []);

  function loadSchedule() {
    api.schedule().then(setSchedule).catch(() => setSchedule(null));
  }

  useEffect(() => {
    if (authed) loadSchedule();
  }, [authed]);

  if (authed === null) return <div className="center muted">Loading…</div>;
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const empty = !schedule || schedule.empty;

  return (
    <div className="app">
      <header>
        <h1>Schedule</h1>
        <nav>
          <button className={tab === "schedule" ? "on" : ""} onClick={() => setTab("schedule")}>
            Schedule
          </button>
          <button className={tab === "calendar" ? "on" : ""} onClick={() => setTab("calendar")}>
            My calendar
          </button>
          <button className={tab === "admin" ? "on" : ""} onClick={() => setTab("admin")}>
            Upload
          </button>
          <button
            className="logout"
            onClick={() => api.logout().then(() => setAuthed(false))}
          >
            Sign out
          </button>
        </nav>
      </header>

      {schedule?.parsed_sheet && (
        <div className="subbar">
          <strong>{schedule.parsed_sheet}</strong>
          {schedule.date_range && (
            <span className="muted">
              {" "}
              · {schedule.date_range.start} → {schedule.date_range.end}
            </span>
          )}
        </div>
      )}

      <main>
        {empty && tab !== "admin" && (
          <p className="muted">No schedule yet. Go to “Upload” to add one.</p>
        )}
        {tab === "schedule" && !empty && <ScheduleGrid schedule={schedule} />}
        {tab === "calendar" && !empty && <MyCalendar schedule={schedule} />}
        {tab === "admin" && <Admin schedule={schedule} onChange={loadSchedule} />}
      </main>
    </div>
  );
}
