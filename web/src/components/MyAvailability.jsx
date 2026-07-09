import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { dateRange, shiftClass, timeLabel } from "../utils.js";

// Members manage their own availability: call out of assigned shifts, offer days
// they can cover, and edit their contact info.
export default function MyAvailability({ schedule, user, onChange }) {
  const person = user?.person;
  const me = useMemo(
    () => (schedule?.people || []).find((p) => p.name === person),
    [schedule, person]);
  const [offers, setOffers] = useState([]);
  const [offerDate, setOfferDate] = useState("");
  const [contact, setContact] = useState((me?.contact || []).join("\n"));
  const [status, setStatus] = useState("");
  const [prefs, setPrefs] = useState({ no_weekdays: [], prefer_nights: false, reminder_minutes: 0 });
  const [swaps, setSwaps] = useState([]);
  const [swap, setSwap] = useState({ a: "", b_person: "", b: "" });

  const dates = dateRange(schedule?.date_range?.start, schedule?.date_range?.end);
  const myOfferDates = offers.filter((o) => o.person === person).map((o) => o.date);
  const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function refresh() {
    api.availability().then(setOffers).catch(() => setOffers([]));
    api.myPrefs().then((p) => setPrefs({ no_weekdays: [], prefer_nights: false, reminder_minutes: 0, ...p })).catch(() => {});
    api.swaps().then(setSwaps).catch(() => setSwaps([]));
  }
  useEffect(() => { refresh(); }, []);
  useEffect(() => { setContact((me?.contact || []).join("\n")); }, [me]);

  function toggleWeekday(i) {
    setPrefs((p) => {
      const s = new Set(p.no_weekdays || []);
      s.has(i) ? s.delete(i) : s.add(i);
      return { ...p, no_weekdays: [...s].sort() };
    });
  }
  async function savePrefs() {
    await api.setMyPrefs(prefs); setStatus("Preferences saved.");
    setTimeout(() => setStatus(""), 1500);
  }
  async function proposeSwap() {
    const mine = shifts[Number(swap.a)];
    const theirs = (others.find((o) => o.name === swap.b_person)?.shifts || [])[Number(swap.b)];
    if (!mine || !swap.b_person || !theirs) { setStatus("Pick your shift, a person, and their shift."); return; }
    await api.proposeSwap({
      a_date: mine.date, a_type: mine.shift_type,
      b_person: swap.b_person, b_date: theirs.date, b_type: theirs.shift_type });
    setStatus("Swap proposed."); refresh(); setTimeout(() => setStatus(""), 1500);
  }
  async function accept(id) { await api.acceptSwap(id); refresh(); }

  if (!person) return <p className="muted">Your account isn’t linked to a name yet.</p>;
  const shifts = me?.shifts || [];
  const others = (schedule?.people || []).filter((p) => p.name !== person);
  const mySwaps = swaps.filter((s) => s.a_person === person || s.b_person === person);

  async function callOut(s) {
    await api.myCallout(s.date, s.shift_type); onChange();
  }
  async function clearOut(s) {
    await api.myCalloutClear(s.date, s.shift_type); onChange();
  }
  async function addOffer() {
    if (!offerDate) return;
    await api.myOffer(offerDate); setOfferDate(""); refresh();
  }
  async function removeOffer(d) {
    await api.myOfferRemove(d); refresh();
  }
  async function saveContact() {
    await api.myContact(contact.split("\n").map((l) => l.trim()).filter(Boolean));
    setStatus("Contact saved."); onChange(); setTimeout(() => setStatus(""), 1500);
  }

  return (
    <div className="card">
      <h2>My availability — {person}</h2>

      <h3>My shifts (call out if you can’t work)</h3>
      <ul className="shift-list">
        {shifts.map((s, i) => (
          <li key={i} className={s.available === false ? "out" : ""}>
            <span className="d">{s.date}</span>
            <span className={shiftClass(s)}>{s.code}</span>
            <span className="m">{s.meaning || ""} ({s.shift_type})</span>
            <span className="t">{timeLabel(s)}</span>
            {s.available === false
              ? <button className="ghost small" onClick={() => clearOut(s)}>undo call-out</button>
              : <button className="ghost small danger" onClick={() => callOut(s)}>can’t work</button>}
          </li>
        ))}
        {shifts.length === 0 && <li className="muted">No shifts this period.</li>}
      </ul>

      <h3>Days I can cover</h3>
      <p className="muted">Offer days you’re free — you’ll show up as a candidate when others call out.</p>
      <div className="row">
        <select value={offerDate} onChange={(e) => setOfferDate(e.target.value)}>
          <option value="">— pick a date —</option>
          {dates.filter((d) => !myOfferDates.includes(d)).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <button className="ghost" onClick={addOffer}>Offer to cover</button>
      </div>
      <ul className="offer-list">
        {myOfferDates.map((d) => (
          <li key={d}>
            <span>{d}</span>
            <button className="ghost small" onClick={() => removeOffer(d)}>remove</button>
          </li>
        ))}
        {myOfferDates.length === 0 && <li className="muted">No offers yet.</li>}
      </ul>

      <h3>My preferences</h3>
      <p className="muted">Used to nudge scheduling and coverage away from days you’d
        rather not work, and to set calendar reminders.</p>
      <div className="row gap" style={{ flexWrap: "wrap" }}>
        <span>Avoid:</span>
        {WD.map((w, i) => (
          <label key={w} className="chk">
            <input type="checkbox" checked={(prefs.no_weekdays || []).includes(i)}
              onChange={() => toggleWeekday(i)} /> {w}
          </label>
        ))}
        <label className="chk">
          <input type="checkbox" checked={!!prefs.prefer_nights}
            onChange={(e) => setPrefs((p) => ({ ...p, prefer_nights: e.target.checked }))} />
          prefer nights
        </label>
        <label>Reminder
          <select value={prefs.reminder_minutes || 0}
            onChange={(e) => setPrefs((p) => ({ ...p, reminder_minutes: Number(e.target.value) }))}>
            <option value={0}>none</option>
            <option value={60}>1h before</option>
            <option value={120}>2h before</option>
            <option value={720}>12h before</option>
          </select>
        </label>
        <button className="ghost" onClick={savePrefs}>Save preferences</button>
      </div>

      <h3>Shift swaps</h3>
      <p className="muted">Propose trading one of your shifts for someone else’s. They
        accept, then a coordinator approves.</p>
      <div className="row gap" style={{ flexWrap: "wrap" }}>
        <label>My shift
          <select value={swap.a} onChange={(e) => setSwap((s) => ({ ...s, a: e.target.value }))}>
            <option value="">—</option>
            {shifts.map((s, i) => s.code && (
              <option key={i} value={i}>{s.date} {s.code} ({s.shift_type})</option>
            ))}
          </select>
        </label>
        <label>With
          <select value={swap.b_person}
            onChange={(e) => setSwap((s) => ({ ...s, b_person: e.target.value, b: "" }))}>
            <option value="">— person —</option>
            {others.map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
          </select>
        </label>
        <label>Their shift
          <select value={swap.b} onChange={(e) => setSwap((s) => ({ ...s, b: e.target.value }))}>
            <option value="">—</option>
            {(others.find((o) => o.name === swap.b_person)?.shifts || []).map((s, i) => s.code && (
              <option key={i} value={i}>{s.date} {s.code} ({s.shift_type})</option>
            ))}
          </select>
        </label>
        <button className="ghost" onClick={proposeSwap}>Propose swap</button>
      </div>
      <ul className="offer-list">
        {mySwaps.map((s) => (
          <li key={s.id}>
            <span>{s.a_person} {s.a_date}({s.a_type}) ⇄ {s.b_person} {s.b_date}({s.b_type})</span>
            <span className={`tag ${s.status === "approved" ? "" : "muted-tag"}`}>{s.status}</span>
            {s.status === "proposed" && s.b_person === person &&
              <button className="ghost small" onClick={() => accept(s.id)}>accept</button>}
          </li>
        ))}
        {mySwaps.length === 0 && <li className="muted">No swaps yet.</li>}
      </ul>

      <h3>My contact info</h3>
      <p className="muted">Shown to admins for coverage calls. One line each (e.g. “C: 555-0100”).</p>
      <textarea rows={3} value={contact} onChange={(e) => setContact(e.target.value)} />
      <div className="row">
        <button onClick={saveContact}>Save contact</button>
        {status && <span className="status">{status}</span>}
      </div>
    </div>
  );
}
