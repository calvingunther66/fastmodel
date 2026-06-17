# Decisions & open items

A record of the choices made while building this (with the schedule owner), the
reasoning, and what's still open. Useful when resuming with no chat history.

## Decisions made

### Parsing
- **"OCR" was a red herring for this file.** The real workbook stores the schedule
  as **cells**, not images, so the data is read directly (exact, no OCR error). The
  generic image/OCR path (`image_extractor.py`, `ocr.py`) is kept for other files
  but isn't used for this roster.
- **Day vs night is positional**, encoded by a code's row offset inside a 3-row
  person block: top = day, middle = midshift (split second-half), bottom = night.
  An earlier version wrongly treated the middle row as night; corrected after the
  owner clarified the three levels.
- **Codes are kept raw and decoded via a single table** (`definitions.py`) into a
  `category` + `meaning`, so undefined codes are never dropped — they pass through
  as `category: "unknown"`.
- **`no` is availability, not a shift** — it marks the person out sick and the
  shift on that date `available: false` (the call-out / coverage workflow).
- **Footer/legend rows are excluded** by bounding the scan to the last named person.
  They had produced phantom `C`/`APP` codes and false warnings.
- **Green vacation fill must not be read as a split** — the split "center bar"
  check only applies when the day-row code is a worked location.

### Codes / timing (from the owner)
- Locations: BC, HC, CV, VLJ, RB, MOS, ENC, NTAS, T. **Clinics = everything that
  isn't BC or HC.** Status: V, R, H (Holiday), A (Available/pool), **OK = A**, BDay,
  no. `*` and `UL` intentionally left undefined.
- Times: night 19:30–08:00; BC day 07:30–20:00; HC day 07:00–19:30; triage
  07:30–18:00; clinic full day 08:00–17:00 (morning 8–12 / afternoon 1–5 when split).
  Confirmed against the sheet's own legend.

### Web app
- **Stack:** FastAPI (reuses the Python parser) + React/Vite, run as **one process**.
- **Hosting:** the owner's **Raspberry Pi 5** at home (always-on → enables a live,
  auto-refreshing calendar feed, which a static host could not).
- **Auth:** a single **shared username/password** gate; each visitor then picks
  their own name. (Not per-person accounts.)
- **Calendar feeds are public-by-token** (`/calendar/<token>.ics`) because calendar
  apps can't log in. The token is the secret and is **stable across re-uploads**
  (`data/tokens.json`) so a subscription never breaks when a new schedule is posted.
- **Schedule input:** admin **uploads** the `.xlsx` through the web UI each period.
- **Timezone:** `America/Los_Angeles` (San Diego), overridable via `TIMEZONE`.

## Open items / future work

- **Clinic split (morning/afternoon)** detection via a coloured center bar is
  implemented but **unverified** — no split appeared in the sample month. Confirm
  against a real split before trusting `split_day`/half-day times.
- **`ENC` / `NTAS`** full names unconfirmed; `NTAS` has no day-time window. `ENC`
  is treated as a clinic but also appears as a night code.
- **`*` and `UL`** remain undefined (owner said to ignore for now).
- **Edge case:** a `BC` on the middle row (e.g. CORTES, tied to a `no`) currently
  gets the BC *day* window even though it's a midshift; it's flagged unavailable so
  it has low impact, but revisit if midshift BC becomes common.
- **Auto-sheet picker** can select a draft tab on upload; the owner should pick the
  canonical tab from the Upload dropdown. Could persist the chosen sheet, or prefer
  tabs without `KH-/NEW-/OLD-` prefixes.
- **Coverage engine (trial, built):** the **Coverage** tab lets an admin mark a
  shift out sick; it flags the shift open, proposes **free** covers (Available
  pool / unscheduled, ranked by qualification + night experience) and **move**
  candidates (people working something reassignable who are qualified), and lets
  the admin **assign** a cover — which injects the shift into that person's grid
  row and live `.ics` feed ("covering for X"). It is a **heuristic** (the workbook
  has no explicit qualifications; "qualified" = has worked that location before).
  It also proposes **cascades** (move a qualified person onto the open shift and
  backfill their vacated slot with a free person — applied as two linked
  call-outs). Lives in `server/coverage.py` + `web/src/components/Coverage.jsx`;
  overrides are stored in `data/overrides.json`. Possible next steps: deeper
  (3+ step) chains, honouring the `R`/note availability hints, and an "undo".
- **Not built:** CSV export; pushing events directly into Google Calendar.
- **HTTPS is required** for Apple/Google calendar subscriptions — see `SERVER.md`
  (Caddy snippet). Remember to set `PUBLIC_BASE_URL` to the https domain so the
  generated `.ics` links are correct.

## Things to be careful with

- **PII:** the real workbook has names + phone numbers. Keep `real_samples/` and
  `data/` out of git (already gitignored). Don't paste real contact info into
  commits, issues, or docs.
- **Change codes/timings in one place:** `schedule_extractor/definitions.py`, and
  add/adjust a test in `tests/test_roster_extractor.py`.
- Run `python -m pytest` after parser changes and `npm run build` after frontend
  changes.
