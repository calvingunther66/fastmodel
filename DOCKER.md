# Docker + Cloudflare Tunnel

Run the whole thing as **one container** that holds both the web app and the
**cloudflared** daemon. cloudflared dials *out* to Cloudflare and securely
tunnels `scheduler.calvingunther.com` to the app — so **no router ports, no
public IP, and no separate HTTPS setup** (Cloudflare terminates TLS at its edge).

```
Internet ──HTTPS──▶ Cloudflare edge ──tunnel──▶ cloudflared ─┐  (same container)
                                                              ├─▶ uvicorn :8000
            scheduler.calvingunther.com                       ┘     (FastAPI app)
```

## Prerequisites

- `calvingunther.com` is on Cloudflare (managed DNS).
- Docker + the Compose plugin on the Pi:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"   # log out/in afterwards
  ```

## 1. Create the tunnel in Cloudflare (one time)

1. Go to **Cloudflare Zero Trust dashboard → Networks → Tunnels → Create a tunnel**.
2. Choose **Cloudflared**, name it (e.g. `schedule`), **Save**.
3. On the install screen, **copy the tunnel token** — the long `eyJ...` string.
   (You don't need to run the install command it shows; the container does that.)
4. Add a **Public Hostname**:
   - **Subdomain:** `scheduler`
   - **Domain:** `calvingunther.com`
   - **Type:** `HTTP`
   - **URL:** `localhost:8000`
     (cloudflared shares the container's network with the app, so `localhost:8000`
     reaches uvicorn.)
5. **Save.** Cloudflare auto-creates the `scheduler` DNS record.

## 2. Configure secrets

```bash
cd fastmodel
cp .env.example .env
# generate a fixed signing key:
python3 -c 'import secrets; print("SECRET_KEY=" + secrets.token_hex(32))'
nano .env      # set APP_PASSWORD, SECRET_KEY, TUNNEL_TOKEN (PUBLIC_BASE_URL is preset)
```

`.env` is gitignored — keep your token and password here, never in git.

## 3. Build and run

```bash
docker compose up -d --build
docker compose logs -f          # watch it connect; Ctrl-C to stop watching
```

You should see uvicorn start and cloudflared register the connection. Then open
**https://scheduler.calvingunther.com**, sign in, go to **Upload**, drop the
`.xlsx`, pick the correct sheet, and share calendar links from **My calendar**.

## 4. Updating later

```bash
cd fastmodel
git pull
docker compose up -d --build    # rebuilds frontend + image, restarts container
```

Your uploaded schedule and calendar tokens live in the `schedule-data` volume,
so they survive rebuilds (calendar links don't change).

## Notes & troubleshooting

- **Data persistence:** uploads/tokens are in the named volume `schedule-data`
  (`docker volume ls`). To start fresh: `docker compose down -v`.
- **HTTPS cookie:** the image sets `SESSION_HTTPS_ONLY=true` (correct behind
  Cloudflare). If you ever run it over plain HTTP, set it to `false`.
- **`.ics` links wrong host:** make sure `PUBLIC_BASE_URL=https://scheduler.calvingunther.com`
  in `.env` — links are built from it, not from the internal request URL.
- **502 from Cloudflare:** the app isn't up yet or the Public Hostname URL isn't
  `localhost:8000`. Check `docker compose logs`.
- **Architecture:** the Dockerfile pulls the cloudflared build matching the
  Pi (arm64) automatically via BuildKit's `TARGETARCH`.
- **Run without Compose** (token via env), if you prefer:
  ```bash
  docker build -t schedule .
  docker run -d --name schedule --restart unless-stopped \
    -e APP_USERNAME=you -e APP_PASSWORD='strong' \
    -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
    -e PUBLIC_BASE_URL=https://scheduler.calvingunther.com \
    -e TUNNEL_TOKEN='eyJ...' \
    -v schedule-data:/data \
    schedule
  ```
- **No tunnel (LAN test):** omit `TUNNEL_TOKEN` and publish the port —
  `docker run -p 8000:8000 ... schedule` — then browse `http://<pi-ip>:8000`.
