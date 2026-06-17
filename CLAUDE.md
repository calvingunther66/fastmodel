# fastmodel — project guide

> Orientation for anyone (human or AI assistant) picking this repo up fresh —
> e.g. a new Claude Code session on the Raspberry Pi with no prior chat history.
> Read this first, then the linked docs for detail.

## What this project is

It extracts a **clinical work schedule from an Excel workbook** and serves it as a
small **web app** with **live per-person calendar feeds** (`.ics`) that phones can
subscribe to. It was built for a midwifery/OB schedule where shifts are encoded by
**position inside a box** (top = day, bottom = night) rather than as plain text.

Two layers:

1. **`schedule_extractor/`** — a Python library/CLI that parses the workbook into
   structured JSON. The important parser is the **roster** parser
   (`roster_extractor.py`); the generic grid/OCR parser is a secondary fallback.
2. **`server/` + `web/`** — a FastAPI backend and a React (Vite) frontend, run as
   **one process**, intended to self-host on a Raspberry Pi behind the user's
   domain. Shared login; admin uploads the `.xlsx`; each person picks their name
   and gets a live calendar link.

## Read next (detailed docs)

| Doc | What's in it |
|-----|--------------|
| **`docs/SCHEDULE_FORMAT.md`** | **The domain knowledge** — exact workbook layout, every shift code, every shift time, colours, availability rules. Most of this came from the schedule owner and is NOT derivable from the code. Start here to understand *why* the parser does what it does. |
| **`docs/DECISIONS.md`** | Decisions made with the owner, rationale, and the list of **open items / future work**. |
| **`DOCKER.md`** | **Primary deploy:** single container bundling the app + cloudflared tunnel, exposed at `scheduler.calvingunther.com` (no open ports). |
| **`DEPLOY_QUICKSTART.md`** | Alternative bare-metal Pi deploy (venv + systemd + Caddy). |
| **`SERVER.md`** | Deploy reference — env vars, HTTPS/Caddy, systemd, and the *why*. |
| **`README.md`** | CLI usage of the extractor + the generic layouts. |

## Repository map

```
schedule_extractor/        Python parser
  roster_extractor.py      ★ main parser: 3-row person blocks, day/mid/night,
                             availability, splits, notes  -> extract_roster(ws)
  definitions.py           ★ codes -> meaning + shift time windows + colour rules
  cli.py / __main__.py     CLI: `python -m schedule_extractor file.xlsx --layout roster`
  workbook.py              generic "auto" layout: routes sheets to cells vs image
  cell_extractor.py        generic date-grid heuristics (fallback)
  image_extractor.py       pull embedded images
  ocr.py                   Tesseract wrapper (optional; degrades if missing)
  output.py / models.py    JSON serialisation + dataclasses (generic layout)

server/                    FastAPI app (serves API + built React app)
  app.py                   routes: /api/*, public /calendar/<token>.ics, SPA
  store.py                 ScheduleStore: upload/parse/persist + tokens + call-outs
  coverage.py              trial: cover-suggestion engine + call-out overrides
  ical.py                  build_ics(): shifts -> VCALENDAR
  config.py                env-var configuration
  __main__.py              `python -m server` (uvicorn)
  requirements.txt         server-only deps

web/                       React + Vite frontend (built to web/dist)
  src/App.jsx              shell: login gate + tabs
  src/components/          Login, ScheduleGrid, MyCalendar, Coverage, Admin
  src/api.js, utils.js     fetch wrapper, date/colour helpers

tests/                     pytest (10 tests) — run with `python -m pytest`
tools/make_sample.py       generate a synthetic workbook for the generic layout
docs/                      detailed documentation (see table above)

Dockerfile                 multi-stage: build web -> python runtime + cloudflared
docker/entrypoint.sh       runs uvicorn + cloudflared together in one container
docker-compose.yml         one-command run; reads secrets from .env
.env.example               template for .env (APP_PASSWORD, SECRET_KEY, TUNNEL_TOKEN)

data/                      RUNTIME state (uploaded xlsx, parsed json, tokens) — gitignored
real_samples/              the owner's real workbook + outputs — gitignored (PII)
```

★ = the files that carry the real logic; start there.

## Quick start

### Parse a workbook to JSON (CLI)
```bash
pip install -r requirements.txt
python -m schedule_extractor path/to/schedule.xlsx --layout roster \
  --sheet "June 21 - July 18, 26" -o out.json --pretty
```

### Run the web app
```bash
pip install -r requirements.txt -r server/requirements.txt
cd web && npm install && npm run build && cd ..
APP_PASSWORD='something' python -m server      # http://localhost:8000
```
Full Pi/deploy instructions: **`SERVER.md`**.

### Tests
```bash
python -m pytest            # 10 tests; all should pass
cd web && npm run build     # frontend must compile
```

## How the data flows

```
.xlsx ──extract_roster()──▶ schedule dict ──ScheduleStore──▶ data/schedule.json
                                   │                               │
                                   │                        /api/schedule (React grid)
                                   └────build_ics()────────▶ /calendar/<token>.ics (live feed)
```

The parsed **schedule dict** is the contract between layers. Its shape (per person:
`shifts[]` with `date/code/shift_type/category/meaning/start/end/crosses_midnight/
available/approved/split_day`, plus `unavailable[]` and `notes[]`) is documented in
`docs/SCHEDULE_FORMAT.md` and produced by `extract_roster` in `roster_extractor.py`.

## Conventions / guardrails

- **Never commit**: `real_samples/` (real names + phone numbers — PII), `data/`
  (runtime uploads/tokens), `web/node_modules/`, `web/dist/`. These are gitignored.
- **Codes/timings live in one place**: `schedule_extractor/definitions.py`. To add
  or change a code, location, or shift time, edit that file (and add a test).
- After changing the parser, run `python -m pytest`. After changing the frontend,
  run `npm run build`.
- The schedule owner is in **San Diego** (Pacific Time); calendar events default to
  `America/Los_Angeles` (override via `TIMEZONE`).

## Known open items

See `docs/DECISIONS.md` for the full list. Highlights:
- The clinic **split** (morning/afternoon via a coloured "center bar") is encoded
  but hasn't been seen in a real file yet, so the detection is unverified.
- `ENC`/`NTAS` full names unconfirmed; `*` and `UL` intentionally left undefined.
- Auto-sheet picker may choose a draft tab; the Upload screen has a sheet dropdown
  to select the correct one (`June 21 - July 18, 26`).
- Not built yet: a "who can cover a called-out shift" view; CSV / push-to-Google
  export.
