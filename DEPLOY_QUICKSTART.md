# Deploy quickstart (Raspberry Pi)

Copy-paste commands to get the schedule app running. For the *why* and for
HTTPS/systemd, see [`SERVER.md`](SERVER.md).

Assumes Raspberry Pi OS (or any Debian/Ubuntu), Python 3.10+, and Node 18+.

## 0. Install prerequisites (once)

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git nodejs npm
```

## 1. Get the code

```bash
git clone https://github.com/calvingunther66/fastmodel.git
cd fastmodel
```

## 2. Python deps (parser + server)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r server/requirements.txt
```

## 3. Build the web frontend

```bash
cd web
npm install
npm run build          # outputs web/dist (served by the API)
cd ..
```

## 4. Run it

```bash
APP_USERNAME=you \
APP_PASSWORD='choose-a-strong-password' \
SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
TIMEZONE=America/Los_Angeles \
python3 -m server
```

Open `http://<your-pi-ip>:8000`, sign in, go to **Upload**, drop the `.xlsx`,
and pick the correct sheet (e.g. `June 21 - July 18, 26`) from the dropdown.
Then go to **My calendar**, choose a name, and copy the live link.

> Tip: save those env vars in a file so you don't retype them:
> ```bash
> cat > .env.sh <<'EOF'
> export APP_USERNAME=you
> export APP_PASSWORD='choose-a-strong-password'
> export SECRET_KEY='paste-a-fixed-hex-key-here'   # fixed = logins survive restarts
> export TIMEZONE=America/Los_Angeles
> export PUBLIC_BASE_URL=https://schedule.yourdomain.com
> EOF
> # then:  source .env.sh && python3 -m server
> ```

## 5. Put it on your domain (recommended)

Calendar subscriptions (Apple/Google) need **HTTPS**. Easiest is Caddy:

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
schedule.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl restart caddy
```

Then set `PUBLIC_BASE_URL=https://schedule.yourdomain.com` (step 4) so the
generated `.ics` links use the public HTTPS URL. Forward router ports **80** and
**443** to the Pi.

## 6. Keep it running on boot (recommended)

```bash
sudo tee /etc/systemd/system/schedule.service >/dev/null <<EOF
[Unit]
Description=Schedule web app
After=network.target

[Service]
WorkingDirectory=$HOME/fastmodel
Environment=APP_USERNAME=you
Environment=APP_PASSWORD=choose-a-strong-password
Environment=SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
Environment=TIMEZONE=America/Los_Angeles
Environment=PUBLIC_BASE_URL=https://schedule.yourdomain.com
ExecStart=$HOME/fastmodel/.venv/bin/python -m server
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now schedule
sudo systemctl status schedule        # check it's running
```

## Updating later

```bash
cd fastmodel
git pull
source .venv/bin/activate
pip install -r requirements.txt -r server/requirements.txt
cd web && npm install && npm run build && cd ..
sudo systemctl restart schedule       # if using systemd
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Page says "frontend not built yet" | Run step 3 (`npm run build`) — `web/dist` must exist. |
| Login fails after restart | Set a **fixed** `SECRET_KEY` (random default changes each start). |
| Calendar won't subscribe on iPhone/Google | You need HTTPS (step 5) and `PUBLIC_BASE_URL` set to the https URL. |
| Upload picks the wrong tab | Use the sheet dropdown on the **Upload** screen to select the canonical tab. |
| `npm`/`node` too old | `sudo npm install -g n && sudo n lts` (or install Node 18+ from NodeSource). |
