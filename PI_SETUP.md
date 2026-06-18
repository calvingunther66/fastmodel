# Pi setup & handoff guide

> **Who this is for:** an assistant (or person) setting this project up **fresh on
> the Raspberry Pi 5** with no prior chat history. It is written so you can go from
> a clean Pi to a working, public `https://scheduler.calvingunther.com` without
> needing anything from the conversations that built it. Read this top-to-bottom
> once, then follow Part B step by step.
>
> **Owner:** Calvin (calvin@calvingunther.com), San Diego / Pacific time.
> **Repo:** `calvingunther66/fastmodel`. Default deploy: **Docker, one container**
> (app + Cloudflare tunnel). Everything mutable lives in a Docker volume so rebuilds
> never lose data.
>
> If anything here disagrees with the code, the **code wins** — tell Calvin so this
> doc can be fixed. Companion docs: `CLAUDE.md` (orientation), `DOCKER.md` (deploy
> detail), `docs/ACCOUNTS.md`, `docs/AUTOMATION.md`, `docs/AGENT_PROMPT.md`,
> `docs/SCHEDULE_FORMAT.md`, `docs/DECISIONS.md`, `DEPLOY_QUICKSTART.md`, `SERVER.md`.

---

## Part A — What this is and how it got here

### A.1 The one-paragraph version

It extracts a **clinical work schedule from an Excel workbook** (a midwifery/OB
roster where shifts are encoded by **position inside a box** — top = day, middle =
midshift, bottom = night — not as plain text) and serves it as a small **web app**
with **live per-person `.ics` calendar feeds** that phones can subscribe to.
Admins upload the `.xlsx`; every clinician gets an account, sees the team schedule,
gets a personal calendar link, can **call out** of their own shifts, and can
**offer days they can cover**. There's a **coverage engine** that proposes who can
fill a called-out shift (and reshuffle around it), an **adaptive, fairness-aware
recommender**, a **leaderboard**, an **audit log**, an in-app **schedule builder**,
and a secure **automation path** (inbox + API token + MCP endpoint) so a scheduled
agent can ingest new months autonomously while schedules are still authored in Excel.

### A.2 The whole story (what was built, in order)

This is the full arc so you understand *why* each piece exists. You don't need to
do anything with this section — it's context.

1. **Extractor prototype.** A Python library/CLI (`schedule_extractor/`) that reads
   an `.xlsx` and emits structured JSON. Originally meant to use OCR, but the real
   workbook stores the schedule as **cells**, so it's read directly and exactly; the
   OCR path (`image_extractor.py`, `ocr.py`) survives as a fallback for image-based
   sheets but isn't used for this roster.

2. **The roster parser** (`schedule_extractor/roster_extractor.py`, the important
   file). The real schedule is **not** a flat grid. Each person is a **3-row block**:
   the name + a code on the **top** row = a **day** shift; a code on the **middle**
   row = a **midshift** (second half of a split day, rare); a code on the **bottom**
   row = a **night** shift. Dates live on row 2 with month rollover. `BC` = Birth
   Center 12-hour. A cell of **`no`** means the person is **out/unavailable** that day
   (this drives call-outs/coverage). Footer/legend rows are excluded; green fill on a
   `V` = approved vacation.

3. **Code & timing definitions** (`schedule_extractor/definitions.py`, the other
   important file — the single source of truth for codes). Locations: `BC`, `HC`,
   `CV`, `VLJ`, `RB`, `MOS`, `ENC`, `NTAS`, `T`. **A clinic = anything that isn't BC
   or HC.** Status codes: `V` vacation, `R` request, `H` holiday, `A`/`OK`
   available-pool, `BDay`, `no` unavailable. Times: night `19:30–08:00`; BC day
   `07:30–20:00`; HC day `07:00–19:30`; triage `07:30–18:00`; clinic full day
   `08:00–17:00` (morning `08–12` / afternoon `13–17` when split via a coloured
   center bar). `*` and `UL` intentionally undefined. **To change any code/time, edit
   this one file and add a test.**

4. **The web app** (`server/` FastAPI + `web/` React/Vite, run as **one process**).
   Behind a login. Each person picks their name and exports a **live calendar link**.
   Calendar feeds are **public-by-token** (`/calendar/<token>.ics`) because calendar
   apps can't log in; the token is stable across re-uploads so subscriptions never
   break.

5. **Containerization** (`Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`).
   **One container** bundles the built frontend, the Python app, and **cloudflared**.
   Cloudflare's tunnel dials *out* and serves `scheduler.calvingunther.com` — **no
   open router ports, no public IP, TLS terminated at Cloudflare's edge.**

6. **Coverage engine** (`server/coverage.py`, `web/src/components/Coverage.jsx`).
   Mark someone out for a shift; the system proposes **free** covers (the Available
   pool / unscheduled people), **move** candidates (reassign someone qualified), and
   multi-step **cascades** (move a qualified person onto the open shift and backfill
   their slot). "Qualified" is heuristic — has worked that location before — until the
   real roster lands.

7. **Dependabot fixes.** Dependency floors bumped (Pillow, python-multipart, FastAPI/
   Starlette, Vite 8 → Node 22 in the Dockerfile).

8. **Real per-person accounts** (`server/accounts.py`, `docs/ACCOUNTS.md`). One
   **bootstrap admin** from env (`APP_USERNAME`/`APP_PASSWORD`), re-synced on every
   startup and `protected` so you can't be locked out. From it, admins create
   accounts that **delegate capabilities** (see A.3). Members self-serve: call out,
   offer cover days, edit own contact, view the team. Passwords are PBKDF2 (stdlib).
   **Everything persists in `DATA_DIR`** (the Docker volume).

9. **Audit log + adaptive scoring** (`server/audit.py`, `server/store.py`). Append-
   only activity log (`data/audit.jsonl`). The recommender accumulates per-person
   history (`data/stats.json`) and gets smarter with use.

10. **Fairness / load-balancing refinement.** People who **consistently step up get
    recommended *less*** and infrequent coverers get a **turn** — so the willing few
    don't burn out. Every recommendation carries a plain-English explanation. A
    **leaderboard** (Insights tab) celebrates who steps up most.

11. **Tunable dial.** A **fairness-vs-competence slider** (`fairness_weight` 0..1,
    default 0.5, `data/settings.json`), surfaced in the Coverage tab. The leaderboard
    (`view_leaderboard`) and the dial (`tune_scoring`) are **separate delegatable
    capabilities**.

12. **Schedule builder (preview)** (`server/store.create_schedule`,
    `web/src/components/Create.jsx`) and a **staff roster** stub
    (`server/roster.py` → `data/roster.json`, **placeholder data for now**). The
    builder makes a schedule without an `.xlsx`; the roster (clinic quals, career/
    per-diem, seniority, no-nights) will later validate assignments and drive
    "qualified for X". **Calvin is finishing the real roster — see Part F.**

13. **Automation / agent access** (`server/apitokens.py`, `server/automation.py`,
    `server/mcp.py`, `docs/AUTOMATION.md`, `docs/AGENT_PROMPT.md`). A scoped, hashed,
    revocable **API token** (`sk_sched_…`, `automate` capability) + an **inbox**
    folder + an **MCP endpoint** at `/claude-mcp` so a scheduled Claude routine can
    find the newest spreadsheet and ingest it idempotently. **This is a documented
    front door with a revocable key, not a hidden auth bypass.**

### A.3 Roles & capabilities (the permission model)

- **admin** — everything (all capabilities implicitly). The bootstrap admin is one.
- **member** — self-service, plus any capabilities an admin grants. Toggleable per
  member:

  | Capability | Grants |
  |------------|--------|
  | `upload` | upload / re-parse schedules; use the Create builder |
  | `manage_coverage` | mark anyone out, assign covers, run cascades, edit any contact |
  | `manage_users` | create / edit / delete accounts; mint API tokens |
  | `view_leaderboard` | see the step-up dashboard (Insights tab) |
  | `tune_scoring` | move the fairness-vs-competence dial |
  | `automate` | use the automation API + the `/claude-mcp` endpoint |

  `view_leaderboard` and `tune_scoring` are independent on purpose.

### A.4 Architecture at a glance

```
Internet ──HTTPS──▶ Cloudflare edge ──tunnel──▶ cloudflared ─┐  (one container)
        scheduler.calvingunther.com                          ├─▶ uvicorn :8000
                                                             ┘     (FastAPI + React)
                                                                       │
   Excel (.xlsx) ─▶ inbox/ ─▶ extract_roster() ─▶ schedule dict ─▶ DATA_DIR (volume)
                                                       │                 │
                                                       ├─▶ /api/schedule (React grid)
                                                       └─▶ /calendar/<token>.ics (live feeds)
```

Data flow contract: the parsed **schedule dict** (per person: `shifts[]` with
`date/code/shift_type/category/meaning/start/end/crosses_midnight/available/
approved/split_day`, plus `unavailable[]` and `notes[]`) is shared by every layer.
Shape documented in `docs/SCHEDULE_FORMAT.md`.

---

## Part B — Set it up on the Pi (Docker, the recommended path)

You'll do this once. Budget ~20 minutes plus build time. Everything in `< >` is a
value you fill in.

### B.0 Prerequisites checklist

- [ ] A Raspberry Pi 5 (arm64, 64-bit OS) with internet, that you can SSH into.
- [ ] `calvingunther.com` is managed on **Cloudflare** (it is).
- [ ] You can log into Calvin's **Cloudflare Zero Trust** dashboard (ask Calvin to
      create the tunnel in B.2 if you can't — you only need the **token** string).
- [ ] The real schedule `.xlsx` on hand (or use the Create builder / a sample first).

### B.1 Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"     # then log out and back in so the group applies
docker --version && docker compose version   # both should print versions
```

### B.2 Create the Cloudflare tunnel (one time)

In **Cloudflare Zero Trust → Networks → Tunnels → Create a tunnel**:

1. Type **Cloudflared**, name it (e.g. `schedule`), **Save**.
2. On the install screen, **copy the tunnel token** — the long `eyJ...` string.
   (You do **not** need to run the install command it shows; the container runs
   cloudflared itself.)
3. Add a **Public Hostname**:
   - Subdomain: `scheduler`
   - Domain: `calvingunther.com`
   - Type: **HTTP**
   - URL: **`localhost:8000`** (cloudflared shares the container's network, so
     `localhost:8000` reaches uvicorn)
4. **Save.** Cloudflare auto-creates the `scheduler` DNS record.

### B.3 Clone the repo

```bash
git clone https://github.com/calvingunther66/fastmodel.git
cd fastmodel
```

> The working branch during development was `claude/schedule-extraction-excel-nag5l7`
> and changes were also pushed to `main`. Deploy from **`main`** unless Calvin says
> otherwise: `git checkout main && git pull`.

### B.4 Configure secrets (`.env`)

```bash
cp .env.example .env
# generate a FIXED signing key (so logins survive restarts):
python3 -c 'import secrets; print("SECRET_KEY=" + secrets.token_hex(32))'
nano .env
```

Fill in `.env` (it is git-ignored — never commit it). Reference:

| Var | Set it to | Notes |
|-----|-----------|-------|
| `APP_USERNAME` | the bootstrap admin login (e.g. `calvin`) | re-synced every boot |
| `APP_PASSWORD` | a **strong** password | this is the admin password; change it here, not in the UI |
| `SECRET_KEY` | the hex string you just generated | keep it fixed; if blank, one is auto-persisted in the volume |
| `PUBLIC_BASE_URL` | `https://scheduler.calvingunther.com` | **must** be the https domain — `.ics` links are built from it |
| `TIMEZONE` | `America/Los_Angeles` | San Diego |
| `TUNNEL_TOKEN` | the `eyJ...` from B.2 | the only thing tying you to Cloudflare |
| `INBOX_HOST` | `./inbox` (default) | host folder bind-mounted to `/inbox`; point at your synced Drive folder if you like |
| `AUTO_INGEST` | `off` (default) | `daily` / `weekly` / `<seconds>` to auto-ingest the inbox without an agent |

`SESSION_HTTPS_ONLY` is forced `true` in compose (correct behind Cloudflare) — leave
it. Only set it `false` if you ever serve plain HTTP on the LAN.

### B.5 Build and run

```bash
docker compose up -d --build
docker compose logs -f          # watch; Ctrl-C stops watching (not the container)
```

In the logs you want to see **uvicorn start** and **cloudflared register a
connection** (it prints the tunnel/connector coming up). First build is slow
(installs Node, builds the React app, pulls cloudflared for arm64).

### B.6 Verify it's live

1. Open **https://scheduler.calvingunther.com** → you should get the login page.
2. Log in with `APP_USERNAME` / `APP_PASSWORD` from `.env`.
3. You should land in the app with admin tabs (Upload, Users, Create, Coverage,
   Insights, Activity, plus the member tabs).

If you get a **502 from Cloudflare**, the app isn't up yet or the Public Hostname
URL isn't exactly `localhost:8000` — check `docker compose logs`.

---

## Part C — First-run configuration (in the web UI)

### C.1 Create accounts for the clinicians

**Users** tab (needs `manage_users`, which the admin has):

- Create one account per person. For each, set a username, a temporary password,
  the **role** (`member` for clinicians), any **capabilities** to delegate (most get
  none; pick a coordinator and give them `manage_coverage`, etc.), and **link them to
  their schedule name** (e.g. `GUNTHER`) so self-service and "My calendar" default to
  them. You can set the link later too.
- The bootstrap admin is `protected` — it can't be deleted/demoted, and its password
  changes only via `APP_PASSWORD` in `.env`.

### C.2 Upload the first schedule

**Upload** tab (needs `upload`):

1. Drop the `.xlsx`.
2. **Pick the correct sheet** in the dropdown. The owner's real workbook has several
   **draft tabs** (names like `KH-2…`, `NEW-3…`, `OLD-3…`, or ending in `(2)`); the
   canonical tab for the sample month is **`June 21 - July 18, 26`**. The auto-picker
   tries to avoid drafts, but **always confirm the tab**.
3. Submit → it parses and becomes the active schedule, feeding the grid, calendar
   tokens, stats, and coverage tools.

### C.3 Share calendar links

**My calendar** tab: each person (or the admin on their behalf) copies their
`/calendar/<token>.ics` URL and **subscribes** in Apple/Google Calendar ("Add
calendar → From URL"). The feed is live: re-uploading a new schedule updates every
subscriber automatically, and the token stays stable so subscriptions never break.

### C.4 Try the coverage workflow (optional sanity check)

**Coverage** tab (admin / `manage_coverage`): mark a person out for a shift → the
system proposes free covers, move candidates, and cascades, each with an explanation.
Assigning a cover injects the shift into that person's grid row and `.ics` feed
("covering for X"). The current dial setting (fairness vs competence) is shown here;
move it in **Insights** if you have `tune_scoring`.

---

## Part D — Automation (feed it from the inbox, autonomously)

This lets a scheduled agent keep the app fed with new months while schedules are
still made in Excel. Full detail: `docs/AUTOMATION.md`; the ready agent prompt:
`docs/AGENT_PROMPT.md`.

### D.1 Where to drop files

- **Docker (this deploy):** the repo's **`inbox/`** folder is bind-mounted to
  `/inbox`. So drop `.xlsx` files in **`<your-clone>/fastmodel/inbox/`** (e.g.
  `/home/pi/fastmodel/inbox/`). Override the host location with `INBOX_HOST` in
  `.env` (point it at a synced Google Drive / rclone / Syncthing folder).
- The newest `.xlsx` wins. Re-dropping the same file is safe (idempotent →
  `unchanged`). A new month is detected as a new period (`added`); an edited file for
  the same period **replaces** it (`updated`). Only `.xlsx`/`.xlsm` are considered;
  Excel lock files (`~$…`) are skipped. **Dropped files are git-ignored (PII).**

### D.2 Mint an API token

**Users → Automation API tokens → Mint token** (needs `manage_users`). Give it the
**`automate`** capability. **Copy the secret now — it's shown once** and stored only
as a SHA-256 hash. Revoke/rotate anytime from the same screen.

### D.3 Point an agent at the MCP endpoint

- Endpoint: **`https://scheduler.calvingunther.com/claude-mcp`**
- Auth header: **`Authorization: Bearer sk_sched_…`** (put the token in the agent's
  secret store, **not** in the prompt).
- Tools: `schedule_status`, `list_spreadsheets`, `inspect_latest` (parses each tab
  **without** importing; returns people/date-range/draft flag + a `suggested_sheet`),
  `ingest_latest` (optional `sheet` arg; returns `added`/`updated`/`unchanged`/`empty`).
- Use the prompt in **`docs/AGENT_PROMPT.md`** verbatim. Its flow: `schedule_status`
  → `inspect_latest` → pick the **canonical, non-draft** tab → `ingest_latest(sheet)`
  → report. Run it on whatever cadence (daily 6am, weekly); it's safe to repeat.

Quick curl smoke test from the Pi (or anywhere):

```bash
curl -s https://scheduler.calvingunther.com/claude-mcp \
  -H "Authorization: Bearer sk_sched_…" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"schedule_status"}}'
```

### D.4 Or skip the agent

- **REST + cron:** `POST /api/automation/ingest-latest` with the bearer token (see
  `docs/AUTOMATION.md` for the cron line).
- **Built-in scheduler:** set `AUTO_INGEST=daily` (or `weekly`/seconds) in `.env`;
  the server ingests the newest inbox file itself, logged as `scheduler`.

---

## Part E — Operating it (updates, persistence, backups)

### E.1 Update to new code later

```bash
cd fastmodel
git pull
docker compose up -d --build
```

**This never touches your data.** All mutable state is in the named volume
`schedule-data` (mounted at `/data`): uploaded workbook, parsed schedule, **accounts**,
calendar tokens, call-outs, availability offers, contact edits, adaptive stats, audit
log, settings, API tokens, and the session signing key. Rebuild only replaces code, so
logins, subscriptions, and history all carry over.

### E.2 Back up / restore the data volume

```bash
# Back up to a tarball in the current dir
docker run --rm -v schedule-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/schedule-data-$(date +%F).tgz -C /data .

# Restore from one
docker run --rm -v schedule-data:/data -v "$PWD":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/schedule-data-YYYY-MM-DD.tgz -C /data"
```

> ⚠️ The **only** command that deletes data is `docker compose down -v` (the `-v`
> drops the volume). Use plain `docker compose down` to stop without data loss.
> Consider a cron'd backup of the volume to off-Pi storage.

### E.3 What lives in `DATA_DIR` (`/data` in the container)

`secret_key`, `users.json`, the parsed `schedule.json`, `tokens.json`,
`overrides.json` (call-outs/covers), `offers`/`contacts`, `stats.json`,
`settings.json` (the dial), `audit.jsonl`, `api_tokens.json`,
`automation_state.json`, and the `inbox/` (bare-metal) — all in the volume.

---

## Part F — What's still open / coming next

- **Real staff roster (in progress, Calvin is finishing it).** Today
  `server/roster.py` holds **placeholder** data (`placeholder: true`). When Calvin
  sends the list — each person's qualified clinics, career vs per-diem, seniority,
  and no-nights flag — it replaces the placeholder and gets wired into: builder
  validation (e.g. block nights for no-nights staff), real "qualified for X" in the
  coverage engine (instead of inferred-from-history), and seniority/per-diem rules.
  Until then, **"qualified" is a heuristic** (has worked that location before).
- **Clinic split (morning/afternoon)** via a coloured center bar is implemented but
  **unverified** — no split appeared in the sample month. Don't fully trust
  `split_day`/half-day times until confirmed against a real split.
- **`ENC` / `NTAS`** full names unconfirmed (`NTAS` has no day window); `*` and `UL`
  intentionally undefined.
- **Not built yet:** CSV export, push-to-Google-Calendar, deeper (3+ step) cascade
  chains, an "undo" for cover assignments.

Full list and rationale: `docs/DECISIONS.md`.

---

## Part G — Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| **502 from Cloudflare** | App not up yet, or Public Hostname URL isn't `localhost:8000`. Check `docker compose logs`. |
| **Can't reach the domain at all** | Tunnel not connected — verify `TUNNEL_TOKEN` in `.env` and that cloudflared registered in the logs. |
| **Login fails for the admin** | `APP_USERNAME`/`APP_PASSWORD` mismatch in `.env`; the admin is re-synced on every boot, so fix `.env` and `docker compose up -d`. |
| **Logged out after every restart** | `SECRET_KEY` not fixed. Set a fixed hex key in `.env` (B.4). |
| **`.ics` links point at the wrong host** | `PUBLIC_BASE_URL` wrong — set it to `https://scheduler.calvingunther.com`. |
| **Login works locally but cookie rejected** | If serving plain HTTP, set `SESSION_HTTPS_ONLY=false`. Behind Cloudflare it must be `true`. |
| **Upload parsed the wrong people / a draft** | Wrong sheet picked. Re-upload and choose the canonical tab (`June 21 - July 18, 26`), not a `KH-/NEW-/OLD-`/`(2)` draft. |
| **Agent ingest says `unchanged` but you want a re-parse** | Call `ingest_latest` with an explicit `sheet` — naming a sheet bypasses the unchanged guard. |
| **Wrong architecture / cloudflared won't run** | The Dockerfile pulls the arch-matched cloudflared via BuildKit `TARGETARCH`; make sure you're building **on** the Pi. |
| **Want a LAN-only test (no tunnel)** | Omit `TUNNEL_TOKEN` and publish the port (uncomment `ports: 8000:8000` in compose), browse `http://<pi-ip>:8000`. |

Run-without-Compose and more notes are in `DOCKER.md`. A **bare-metal** alternative
(venv + systemd + Caddy, no Docker) is in `DEPLOY_QUICKSTART.md` / `SERVER.md`.

---

## Part H — Guardrails (do not violate)

- **Never commit:** `real_samples/` (real names + phone numbers — PII), `data/`
  (runtime state/tokens), `web/node_modules/`, `web/dist/`, `.env`, or any dropped
  `inbox/` spreadsheet. All are git-ignored — keep it that way. Don't paste real
  contact info into commits, issues, or docs.
- **Codes/timings change in one place:** `schedule_extractor/definitions.py` (and add
  a test in `tests/test_roster_extractor.py`).
- After parser changes run `python -m pytest`; after frontend changes run
  `cd web && npm run build`. Both must be green before deploying.
- This is a real clinic schedule — be conservative. When unsure about a parsing rule
  or a coverage decision, ask Calvin rather than guessing.

---

## Part I — Quick command reference

```bash
# --- one-time setup ---
curl -fsSL https://get.docker.com | sh ; sudo usermod -aG docker "$USER"   # then re-login
git clone https://github.com/calvingunther66/fastmodel.git && cd fastmodel
cp .env.example .env ; nano .env        # set APP_PASSWORD, SECRET_KEY, TUNNEL_TOKEN
docker compose up -d --build

# --- day to day ---
docker compose logs -f                  # watch logs
git pull && docker compose up -d --build   # deploy new code (keeps all data)
docker compose down                     # stop (data safe)
# docker compose down -v                # ⚠️ stop AND DELETE the data volume

# --- dev checks (in the repo) ---
python -m pytest                        # backend tests (should be all green)
cd web && npm run build                 # frontend must compile

# --- backup the data volume ---
docker run --rm -v schedule-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/schedule-data-$(date +%F).tgz -C /data .
```

---

## Part J — File map (where everything lives)

```
schedule_extractor/
  roster_extractor.py   ★ main parser: 3-row blocks, day/mid/night, availability, notes
  definitions.py        ★ codes → meaning + shift-time windows + colour rules
  cli.py / __main__.py  CLI: python -m schedule_extractor file.xlsx --layout roster
  workbook.py / cell_extractor.py / image_extractor.py / ocr.py   generic fallback paths
  output.py / models.py JSON serialisation + dataclasses

server/                 FastAPI app (serves API + built React)
  app.py                routes: auth, /api/*, self-service, /calendar/<token>.ics, /claude-mcp, SPA
  accounts.py           AccountStore: users.json, PBKDF2, roles + capabilities
  apitokens.py          ApiTokenStore: hashed sk_sched_ bearer tokens
  automation.py         inbox scan + idempotent ingest (added/updated/unchanged/empty)
  mcp.py                minimal MCP JSON-RPC server for the agent endpoint
  store.py              ScheduleStore: upload/parse/persist, tokens, call-outs, offers, stats
  coverage.py           cover-suggestion engine (free/move/cascade), adaptive + fairness scoring
  roster.py             StaffRoster: roster.json (PLACEHOLDER staff + attributes)
  audit.py              AuditLog: append-only audit.jsonl
  ical.py               build_ics(): shifts → VCALENDAR
  config.py             env-var config + persistent SECRET_KEY
  __main__.py           python -m server (uvicorn)

web/src/components/      Login, ScheduleGrid, MyCalendar, MyAvailability, Coverage,
                         Admin (upload + automation), Create (builder), Users (+ API tokens),
                         Insights (leaderboard + dial), Activity

Dockerfile               multi-stage: build web → python runtime + cloudflared + tini
docker/entrypoint.sh     runs uvicorn + cloudflared together
docker-compose.yml       one-command run; reads .env
.env.example             template (APP_PASSWORD, SECRET_KEY, TUNNEL_TOKEN, INBOX_HOST, AUTO_INGEST)
inbox/                   drop .xlsx here (bind-mounted to /inbox); README kept, files ignored
data/                    RUNTIME state (the Docker volume) — git-ignored
tests/                   pytest suite — run with python -m pytest
```

★ = the files carrying the real logic; start there if you touch parsing.
