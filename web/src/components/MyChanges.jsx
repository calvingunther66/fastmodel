import React, { useEffect, useState } from "react";
import { api } from "../api.js";

// "What changed for me" feed (J1). Pull-only — no notifications. New-since-last-
// visit items are marked using a localStorage high-water mark.
export default function MyChanges({ person }) {
  const [items, setItems] = useState([]);
  const [feedUrl, setFeedUrl] = useState("");
  const seenKey = `changes-seen:${person || ""}`;
  const [lastSeen] = useState(() => localStorage.getItem(seenKey) || "");

  useEffect(() => {
    api.myChanges().then((rows) => {
      setItems(rows);
      if (rows.length) localStorage.setItem(seenKey, rows[0].ts);
    }).catch(() => setItems([]));
    if (person) {
      api.people().then((ps) => {
        const me = ps.find((p) => p.name === person);
        if (me?.feed_url) setFeedUrl(me.feed_url);
      }).catch(() => {});
    }
  }, [seenKey, person]);

  if (items.length === 0) return null;
  const newCount = items.filter((i) => i.ts > lastSeen).length;

  return (
    <div className="card my-changes">
      <h3>What changed for you
        {newCount > 0 && <span className="count-badge">{newCount} new</span>}
        {feedUrl && <a className="feed-link" href={feedUrl} title="Subscribe (Atom feed)">⤵ feed</a>}</h3>
      <ul className="change-list">
        {items.slice(0, 20).map((it, i) => (
          <li key={i} className={it.ts > lastSeen ? "fresh" : ""}>
            <span className="change-when">{new Date(it.ts).toLocaleDateString(undefined,
              { month: "short", day: "numeric" })}</span>
            <span className="change-text">{it.summary}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
