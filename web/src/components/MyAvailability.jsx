import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { dateRange, timeLabel } from "../utils.js";

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

  const dates = dateRange(schedule?.date_range?.start, schedule?.date_range?.end);
  const myOfferDates = offers.filter((o) => o.person === person).map((o) => o.date);

  function refresh() {
    api.availability().then(setOffers).catch(() => setOffers([]));
  }
  useEffect(() => { refresh(); }, []);
  useEffect(() => { setContact((me?.contact || []).join("\n")); }, [me]);

  if (!person) return <p className="muted">Your account isn’t linked to a name yet.</p>;
  const shifts = me?.shifts || [];

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
            <span className="c">{s.code}</span>
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
