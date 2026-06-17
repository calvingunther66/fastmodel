import React from "react";
import { dateRange, dayLabel, shiftClass, timeLabel } from "../utils.js";

export default function ScheduleGrid({ schedule }) {
  const range = schedule?.date_range || {};
  const dates = dateRange(range.start, range.end);
  const people = (schedule?.people || []).filter((p) => p.name);

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
                        <span
                          key={i}
                          className={shiftClass(s)}
                          title={`${s.meaning || s.code}${
                            timeLabel(s) ? " · " + timeLabel(s) : ""
                          }${s.available === false ? " · NEEDS COVERAGE" : ""}`}
                        >
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
