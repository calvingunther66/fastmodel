# Inbox — drop your schedule spreadsheets here

This folder is where you put the Excel schedule. The app/automation always picks
up the **newest `.xlsx`** here and ingests it.

## Where this folder actually is

- **Docker (the Pi deploy):** this repo's `inbox/` is bind-mounted into the
  container at `/inbox` (see `docker-compose.yml`). So drop files in
  **`<your-clone>/fastmodel/inbox/`** on the Pi — e.g. `/home/pi/fastmodel/inbox/`.
  Override the host location by setting `INBOX_HOST` in `.env`.
- **Bare-metal (no Docker):** it's `data/inbox/` next to the app (override with the
  `INBOX_DIR` env var).

## How to get files here

Use whatever sync you like — the app just watches the folder:

- Google Drive desktop / OneDrive: sync a folder, point `INBOX_HOST` at it.
- `rclone copy gdrive:Schedules ./inbox` on a timer.
- `scp schedule.xlsx pi@pi:~/fastmodel/inbox/`
- Syncthing a folder to the Pi.

## Notes

- Only `.xlsx`/`.xlsm` files are considered; everything else (like this README) is
  ignored. Excel lock files (`~$…`) are skipped.
- Re-dropping the same file is safe — ingestion is idempotent (it reports
  `unchanged`).
- A new month's file is detected as a new period and **added**; an updated file for
  the same period **replaces** it.
- Dropped spreadsheets are git-ignored (they contain real names/phone numbers).
