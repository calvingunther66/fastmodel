import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { dateRange, dayLabel, shiftClass, timeLabel } from "../utils.js";

const LEVELS = [
  ["day", "Day"],
  ["midshift", "Mid"],
  ["night", "Night"],
];

export default function ScheduleGrid({ schedule, user }) {
  const range = schedule?.date_range || {};
  const dates = dateRange(range.start, range.end);
  const allPeople = (schedule?.people || []).filter((p) => p.name);
  const today = new Date().toISOString().slice(0, 10);
  const todayInRange = dates.includes(today);

  const [view, setView] = useState(
    typeof window !== "undefined" && window.innerWidth < 720 ? "agenda" : "grid",
  );
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("all");
  const [mine, setMine] = useState(false);
  const [holidays, setHolidays] = useState({});
  useEffect(() => {
    api.holidays()
      .then((hs) => setHolidays(Object.fromEntries(hs.map((h) => [h.date, h.label || "holiday"]))))
      .catch(() => setHolidays({}));
  }, []);

  if (!dates.length) return <p className="muted">No schedule loaded yet.</p>;

  // Apply person-level filters (name search + "just me").
  const needle = q.trim().toLowerCase();
  const people = allPeople.filter((p) => {
    if (mine && user?.person && p.name !== user.person) return false;
    if (needle && !p.name.toLowerCase().includes(needle)) return false;
    return true;
  });

  // Index shifts by person + date, honouring the shift-type filter.
  const shiftOk = (s) => level === "all" || s.shift_type === level;
  const byPerson = new Map();
  for (const p of people) {
    const m = new Map();
    for (const s of p.shifts) {
      if (!shiftOk(s)) continue;
      if (!m.has(s.date)) m.set(s.date, []);
      m.get(s.date).push(s);
    }
    byPerson.set(p.name, m);
  }

  function jumpToToday() {
    if (view !== "agenda") setView("agenda");
    requestAnimationFrame(() =>
      document.getElementById("agenda-today")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  return (
    <div className="schedule-view">
      <div className="filter-bar">
        <div className="view-toggle" role="tablist" aria-label="Schedule view">
          <button role="tab" aria-selected={view === "grid"}
            className={view === "grid" ? "on" : ""} onClick={() => setView("grid")}>Grid</button>
          <button role="tab" aria-selected={view === "agenda"}
            className={view === "agenda" ? "on" : ""} onClick={() => setView("agenda")}>By day</button>
        </div>
        <input className="filter-search" type="search" placeholder="Search name…"
          aria-label="Search by name" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by shift" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="all">All shifts</option>
          {LEVELS.map(([k, l]) => <option key={k} value={k}>{l} only</option>)}
        </select>
        {user?.person && (
          <label className="chk">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            Just me
          </label>
        )}
        {todayInRange && (
          <button className="ghost small" onClick={jumpToToday}>Jump to today</button>
        )}
      </div>
      {people.length === 0
        ? <p className="muted">No people match your filters.</p>
        : view === "grid"
          ? <GridView dates={dates} people={people} byPerson={byPerson} today={today} holidays={holidays} />
          : <AgendaView dates={dates} people={people} byPerson={byPerson} today={today} holidays={holidays} />}
    </div>
  );
}

function GridView({ dates, people, byPerson, today, holidays }) {
  return (
    <div className="grid-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th className="sticky name-col">Name</th>
            {dates.map((d) => {
              const { dom, dow, weekend } = dayLabel(d);
              const hol = holidays[d];
              return (
                <th key={d} title={hol || undefined}
                  className={`${weekend ? "weekend" : ""}${d === today ? " today-col" : ""}${hol ? " holiday-col" : ""}`}>
                  <div className="dom">{dom}</div>
                  <div className="dow">{hol ? "★" : dow}</div>
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
                {dates.map((d) => (
                  <td key={d} className={d === today ? "today-col" : ""}>
                    {(m.get(d) || []).map((s, i) => (
                      <span key={i} className={shiftClass(s)} title={shiftTitle(s)}>{s.code}</span>
                    ))}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AgendaView({ dates, people, byPerson, today, holidays }) {
  return (
    <div className="agenda">
      {dates.map((d) => {
        const { dom, dow, weekend } = dayLabel(d);
        const hol = holidays[d];
        const groups = { day: [], midshift: [], night: [], other: [] };
        for (const p of people) {
          for (const s of (byPerson.get(p.name).get(d) || [])) {
            const g = groups[s.shift_type] ? s.shift_type : "other";
            groups[g].push({ name: p.name, s });
          }
        }
        const total = Object.values(groups).reduce((n, a) => n + a.length, 0);
        return (
          <section key={d} id={d === today ? "agenda-today" : undefined}
            className={`agenda-day${weekend ? " weekend" : ""}${d === today ? " today" : ""}${hol ? " holiday" : ""}`}>
            <h3>
              {dow} {dom}
              {d === today && <span className="today-tag">today</span>}
              {hol && <span className="holiday-tag">★ {hol}</span>}
            </h3>
            {total === 0 && <p className="muted small">Nobody scheduled.</p>}
            {[...LEVELS, ["other", "Other"]].map(([key, label]) => (
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
