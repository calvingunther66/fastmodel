import React, { useState } from "react";
import { dateRange, dayLabel, shiftClass, timeLabel } from "../utils.js";

const LEVELS = [
  ["day", "Day"],
  ["midshift", "Mid"],
  ["night", "Night"],
];

export default function ScheduleGrid({ schedule }) {
  const range = schedule?.date_range || {};
  const dates = dateRange(range.start, range.end);
  const people = (schedule?.people || []).filter((p) => p.name);
  // Default to the agenda view on narrow screens (phones), grid on desktop.
  const [view, setView] = useState(
    typeof window !== "undefined" && window.innerWidth < 720 ? "agenda" : "grid",
  );

  if (!dates.length) return <p className="muted">No schedule loaded yet.</p>;

  // Index shifts by person + date for quick lookup.
  const byPerson = new Map();
  for (const p of people) {
    const m = new Map();
    for (const s of p.shifts) {
      if (!m.has(s.date)) m.set(s.date, []);
      m.get(s.date).push(s);
    }
    byPerson.set(p.name, m);
  }

  return (
    <div className="schedule-view">
      <div className="view-toggle" role="tablist" aria-label="Schedule view">
        <button role="tab" aria-selected={view === "grid"}
          className={view === "grid" ? "on" : ""} onClick={() => setView("grid")}>
          Grid
        </button>
        <button role="tab" aria-selected={view === "agenda"}
          className={view === "agenda" ? "on" : ""} onClick={() => setView("agenda")}>
          By day
        </button>
      </div>
      {view === "grid"
        ? <GridView dates={dates} people={people} byPerson={byPerson} />
        : <AgendaView dates={dates} people={people} byPerson={byPerson} />}
    </div>
  );
}

function GridView({ dates, people, byPerson }) {
  return (
    <div className="grid-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th className="sticky name-col">Name</th>
            {dates.map((d) => {
              const { dom, dow, weekend } = dayLabel(d);
              return (
                <th key={d} className={weekend ? "weekend" : ""}>
                  <div className="dom">{dom}</div>
                  <div className="dow">{dow}</div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {people.map((p) => {
            const m = byPerson.get(p.name);
            return (
              <tr key={p.name}>
                <td className="sticky name-col">{p.name}</td>
                {dates.map((d) => {
                  const shifts = m.get(d) || [];
                  return (
                    <td key={d}>
                      {shifts.map((s, i) => (
                        <span key={i} className={shiftClass(s)} title={shiftTitle(s)}>
                          {s.code}
                        </span>
                      ))}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AgendaView({ dates, people, byPerson }) {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="agenda">
      {dates.map((d) => {
        const { dom, dow, weekend } = dayLabel(d);
        // Collect everyone working this date, grouped by shift level.
        const groups = { day: [], midshift: [], night: [], other: [] };
        for (const p of people) {
          for (const s of (byPerson.get(p.name).get(d) || [])) {
            const g = groups[s.shift_type] ? s.shift_type : "other";
            groups[g].push({ name: p.name, s });
          }
        }
        const total = Object.values(groups).reduce((n, a) => n + a.length, 0);
        return (
          <section key={d} className={`agenda-day${weekend ? " weekend" : ""}${d === today ? " today" : ""}`}>
            <h3>
              {dow} {dom}
              {d === today && <span className="today-tag">today</span>}
            </h3>
            {total === 0 && <p className="muted small">Nobody scheduled.</p>}
            {LEVELS.map(([key, label]) => (
              groups[key].length > 0 && (
                <div key={key} className="agenda-level">
                  <span className="agenda-level-label">{label}</span>
                  <div className="agenda-people">
                    {groups[key].map(({ name, s }, i) => (
                      <span key={i} className={shiftClass(s)} title={shiftTitle(s)}>
                        {name} · {s.code}
                      </span>
                    ))}
                  </div>
                </div>
              )
            ))}
            {groups.other.length > 0 && (
              <div className="agenda-level">
                <span className="agenda-level-label">Other</span>
                <div className="agenda-people">
                  {groups.other.map(({ name, s }, i) => (
                    <span key={i} className={shiftClass(s)} title={shiftTitle(s)}>
                      {name} · {s.code}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function shiftTitle(s) {
  return `${s.meaning || s.code}${timeLabel(s) ? " · " + timeLabel(s) : ""}` +
    `${s.available === false ? " · NEEDS COVERAGE" : ""}`;
}
