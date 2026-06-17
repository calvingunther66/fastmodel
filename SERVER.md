# Schedule web app — running on a Raspberry Pi

A small **FastAPI** server that:

- gates the schedule behind a **shared username/password**,
- lets an admin **upload** the `.xlsx` each period (parsed with `schedule_extractor`),
- shows the schedule in a **React** UI, and
- serves a **live, per-person `.ics` calendar feed** at a secret-token URL that
  Google/Apple/Outlook can subscribe to and auto-refresh.

One process serves both the API and the built React app.

## Architecture

```
Browser ──▶  FastAPI (server/)         ──▶  schedule_extractor (Excel parser)
   │           ├─ /api/*  (login, schedule, upload)   session cookie
   │           ├─ /calendar/<token>.ics  (PUBLIC live feed, token = secret)
   └─ React ◀──┴─ /  (serves web/dist)
```

- **Login**: one shared `APP_USERNAME` / `APP_PASSWORD`, stored as a signed
  session cookie. Each visitor then picks their own name.
- **Calendar feeds are public by token**: calendar apps can't log in, so each
  person's feed lives at `/calendar/<random-token>.ics`. The token is the secret;
  it stays stable across re-uploads so subscriptions never break.

## One-time setup on the Pi

```bash
# 1. Python deps (core parser + server)
pip install -r requirements.txt -r server/requirements.txt

# 2. Build the React frontend (needs Node 18+)
cd web && npm install && npm run build && cd ..
```

## Configure (environment variables)

| Variable          | Purpose                                   | Default               |
|-------------------|-------------------------------------------|-----------------------|
| `APP_USERNAME`    | shared login username                     | `admin`               |
| `APP_PASSWORD`    | shared login password — **set this!**     | `changeme`            |
| `SECRET_KEY`      | session-cookie signing key (set a fixed one so logins survive restarts) | random per start |
| `TIMEZONE`        | Olson tz for calendar events              | `America/Los_Angeles` |
| `PUBLIC_BASE_URL` | external URL used in `.ics` links, e.g. `https://schedule.example.com` | derived from request |
| `HOST` / `PORT`   | bind address / port                       | `0.0.0.0` / `8000`    |
| `DATA_DIR`        | where uploads/tokens are stored           | `./data`              |

## Run

```bash
APP_USERNAME=you APP_PASSWORD='a-strong-password' \
SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')" \
PUBLIC_BASE_URL="https://schedule.example.com" \
python -m server
```

Then open `http://<pi-ip>:8000`, sign in, go to **Upload**, drop your `.xlsx`,
and (if needed) pick the correct sheet from the dropdown.

## Exposing it on your domain

Point your domain at the Pi and put **HTTPS** in front (Apple Calendar and Google
require `https`/`webcal` for subscriptions). Easiest is [Caddy](https://caddyserver.com),
which gets a free certificate automatically:

```
schedule.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Set `PUBLIC_BASE_URL=https://schedule.example.com` so the generated calendar
links use the public HTTPS URL. Forward port 443 (and 80 for the cert) on your
router to the Pi.

### Keep it running

Run it under systemd so it restarts on boot/crash. Example
`/etc/systemd/system/schedule.service`:

```ini
[Unit]
Description=Schedule web app
After=network.target

[Service]
WorkingDirectory=/home/pi/fastmodel
Environment=APP_USERNAME=you
Environment=APP_PASSWORD=a-strong-password
Environment=SECRET_KEY=<paste a fixed hex key>
Environment=PUBLIC_BASE_URL=https://schedule.example.com
ExecStart=/usr/bin/python3 -m server
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now schedule
```

## Development (two terminals)

```bash
# terminal 1 — API with autoreload
APP_PASSWORD=test RELOAD=1 python -m server
# terminal 2 — Vite dev server (proxies /api and /calendar to :8000)
cd web && npm run dev
```

Open the Vite URL (usually http://localhost:5173).
