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

### Accounts & persistence
- **Per-person accounts** replaced the shared password. Roles `admin`/`member`
  plus delegatable capabilities (`upload`, `manage_coverage`, `manage_users`) —
  chosen over fixed roles so an admin can hand out specific powers. A bootstrap
  admin is defined by env (`APP_USERNAME`/`APP_PASSWORD`), re-synced on startup
  and `protected` so you can't be locked out. Passwords are PBKDF2 (stdlib).
- **Members self-serve:** call out of their own shifts, offer days they can cover
  (which boosts them in coverage proposals), edit their own contact info, and view
  the whole team. See `docs/ACCOUNTS.md`.
- **Everything persists in `DATA_DIR`** (the Docker volume): accounts, schedule,
  tokens, call-outs, offers, contact edits, adaptive stats, the activity log, and a
  persisted `secret_key` so logins survive restarts/rebuilds. `docker compose up -d
  --build` never resets data; only `down -v` deletes the volume. Backup/restore in
  `DOCKER.md`.

### Activity log & adaptive scoring
- **Activity log** (`server/audit.py` → `data/audit.jsonl`): append-only record of
  logins, uploads, call-outs, assignments, and account changes. Viewable by admins
  / oversight (`manage_users` or `manage_coverage`) at `/api/audit` and the
  **Activity** tab.
- **Adaptive coverage scoring**: the store accumulates per-person history in
  `data/stats.json` — how much each person works each location/shift (folded from
  every uploaded schedule, keyed by date-range so re-parsing the same period doesn't
  double-count) and how often they've **stepped up to cover** (incremented on each
  assignment). `coverage.propose(..., stats=...)` folds in two signals:
  - **competence** (works this location/shift often) → small positive (familiarity);
  - **fairness / load-balancing** → the cover count is compared to the team average;
    people who've covered a lot get **eased off** and those who rarely cover get a
    **turn**. This deliberately spreads the load so the willing few don't burn out
    (a refinement of the original "reward reliability" idea, at the owner's request).
  Each candidate carries a plain-English `explanation` plus detailed `reasons`.
  Bonuses are additive on top of the static heuristics; with no history, behaviour
  is unchanged.
- **Step-up dashboard** (`/api/coverage/leaderboard`, **Insights** tab): ranks who
  covers the most, with per-person cover/work breakdowns. It celebrates the reliable
  folks while the recommender gives others the next turn.
- **Tunable dial** (`/api/coverage/settings`, `fairness_weight` 0..1, default 0.5,
  persisted in `data/settings.json`): a slider in the Insights tab dials competence
  vs fairness (0 = pure competence/availability, 1 = pure load-balancing).
- **Two new delegatable capabilities**, deliberately independent so the leaderboard
  and the dial can be handed out separately: `view_leaderboard` (see the dashboard)
  and `tune_scoring` (move the dial). Both are admin-implicit.

### Schedule creation (preview) & staff roster
- **In-app schedule builder** (`/api/schedule/create`, **Create** tab, `upload`
  cap): build a schedule without an `.xlsx` — pick a period, then set day/mid/night
  codes per person on a grid. `store.create_schedule()` decodes codes to
  meaning+times via `definitions`, so a created schedule is identical in shape to a
  parsed one and becomes the active schedule (feeding tokens, stats, coverage).
- **Staff roster** (`server/roster.py` → `data/roster.json`): the master list of
  people and attributes — clinics qualified, career/per-diem, seniority,
  works_nights. **Currently placeholder data** (`placeholder: true`). The owner will
  send the real roster; `replace()` / a future `/api/roster` POST swaps it in.
  Intended next uses: validate assignments (e.g. block nights for no-nights staff —
  the grid already greys those cells), drive "qualified for X" in coverage from real
  quals instead of inferred history, and respect seniority/per-diem rules.

### Automation & agent (MCP) access
- **Reframed "backdoor" as a secure, scoped automation interface** — explicitly not
  a hidden/auth-bypassing path. Headless access uses **API tokens** (`server/
  apitokens.py`, `data/api_tokens.json`): random `sk_sched_…` secrets stored only as
  SHA-256 hashes, scoped to capabilities, revocable, shown once, audit-logged.
- **New `automate` capability** gates the automation routes and the MCP endpoint.
- **Inbox + idempotent ingest** (`server/automation.py`): the newest `.xlsx` in
  `INBOX_DIR` is ingested with change detection (`unchanged`/`updated`/`added`),
  state in `data/automation_state.json`. Sync method (Drive/rclone/scp) is the
  owner's choice; we just watch the folder.
- **MCP endpoint** `/claude-mcp` (`server/mcp.py`): minimal JSON-RPC server exposing
  `list_spreadsheets`, `ingest_latest`, `schedule_status` so a scheduled Claude
  routine can drive ingestion. Three run modes: MCP agent, REST+cron, or the
  built-in `AUTO_INGEST` scheduler. All over the HTTPS tunnel. See `docs/AUTOMATION.md`.
- The inbox is a Docker bind-mount (`INBOX_HOST:/inbox`) so files synced on the host
  are visible to the container.
- **New MCP tools** `validate_latest` (runs the validator on the active schedule) and
  `coverage_plan` (read-only ranked cover plan), injected into `mcp.handle` via a
  `services` dict so the module stays decoupled from the app.

### Big adaptive feature batch (per-feature delegatable)
A large batch was added to make the system more adaptive, with **granular
capabilities** so each feature delegates one by one or in small groups (presets:
Coordinator / Scheduler / Analyst / Automation). Notifications were deliberately
**sidelined** for now. Highlights (all additive; default behaviour unchanged when the
roster is still placeholder):
- **Roster-aware engine (A1)** — the real roster's `clinics` drive qualification and
  `works_nights` is a **hard block** on night assignments; per-diem is favoured as the
  flex pool. Falls back to the work-history heuristic while the roster is placeholder.
  `roster.engine_quals()` → `coverage.propose(roster=…)`. Editable in the **Roster** tab.
- **Validator + fatigue (A2/A3, `server/validate.py`)** — flags unqualified,
  no-nights, double-booking, understaffed (opt-in minimums), unknown codes (ignores
  `*`/`UL`), plus fatigue (consecutive days, short rest, weekly hours). Shown in the
  Upload tab and exposed at `/api/schedule/issues` + the `validate_latest` MCP tool.
  Tuned against the real workbook: minimums **off by default** (it's availability-
  oriented), so no false "understaffed" spam.
- **Learned affinity (A4)** — people who have actually covered a location get a small
  competence boost (uses existing cover-by-code data).
- **Generator (C1, `server/generator.py`)** — greedy, fairness-aware drafting honouring
  quals/no-nights/prefs/coverage goals; returns `create_schedule`-shaped assignments
  loaded into the Create grid for editing (nothing saved until "Create"). What-if
  **simulate** (C2) and builder **templates** (C3) added too.
- **Open-shift claims (B1)** — members claim shifts they're eligible for; coordinators
  approve (`assign_cover`). **Shift swaps (B3)** — propose → accept → `manage_swaps`
  approves, applied via `coverage.apply_swaps`. **Member preferences (B4)** —
  avoid-days, prefer-nights, calendar-reminder; feed coverage, generator, validator, ICS.
- **Equity dashboard (D1)** — leaderboard gains nights/weekends/holidays/hours.
  **CSV exports (D2, `server/exports.py`)**. **ICS niceties (D3)** — VALARM reminders,
  LOCATION, categories.
- **Ops** — `/healthz` (E3). Login lockout / 2FA (F) noted but not in this batch.

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
- **Now built** (see "Big adaptive feature batch" above): CSV export, an open-shift
  "who can cover" view (member claims + approve), shift swaps, the schedule generator,
  the validator, and member preferences. **Still not built:** push events directly
  into Google Calendar; notifications (email/push) — deliberately sidelined; the
  security items (login lockout, admin 2FA, member password-reset flow).
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
