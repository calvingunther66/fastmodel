# Automation & the agent (MCP) endpoint

Lets an authorized agent (e.g. a scheduled Claude routine) **check Excel, find the
latest spreadsheet, and feed it into the app autonomously** — while schedules are
still authored in Excel, until that's phased out.

> **This is not a hidden backdoor.** It's a front door with a revocable key: a
> scoped, hashed, audit-logged **API token**, going through the same capability
> checks as everything else, only over your HTTPS Cloudflare tunnel. You mint it,
> you can revoke it, and every use is recorded in the Activity log.

## How it works

```
your Excel ──sync──▶ INBOX_DIR (on the Pi) ──▶ "ingest latest" ──▶ app
   (Drive/rclone/scp)        newest .xlsx          idempotent       (active schedule)
```

- **Inbox**: a folder the Pi watches (`INBOX_DIR`, default `data/inbox`). Sync your
  schedule files there however you like (Google Drive desktop, rclone, Syncthing,
  scp). The newest `.xlsx` wins.
- **Idempotent ingest**: each run reports one of
  - `unchanged` — same file content as last time (no-op),
  - `updated` — same schedule period, new content → replaces,
  - `added` — a new month/period → becomes active.
  State is tracked in `data/automation_state.json`, so daily/weekly runs are safe.

## 1. Mint an API token

In the app: **Users → Automation API tokens → Mint token** (needs `manage_users`).
Give it the **`automate`** capability. Copy the secret — it's shown **once** and
stored only as a hash. Revoke anytime from the same screen.

(The token also works as a normal bearer credential on `/api/*` for whatever
capabilities you grant it.)

## 2. Three ways to run it

### a) Agent via MCP (the `/claude-mcp` endpoint)
A minimal MCP server lives at **`https://scheduler.calvingunther.com/claude-mcp`**,
authenticated by the bearer token. Tools:

| Tool | What it does |
|------|--------------|
| `list_spreadsheets` | inbox files, newest first |
| `inspect_latest` | parse the newest file per tab **without** importing; returns people counts, date ranges, draft flags, and a `suggested_sheet` |
| `ingest_latest` | ingest the newest (optional `sheet` arg); returns added/updated/unchanged |
| `schedule_status` | active schedule + automation state |
| `validate_latest` | run the validator on the active schedule; returns problems (unqualified, no-nights, double-booking, understaffed, fatigue) + a summary |
| `coverage_plan` | read-only ranked coverage plan for an open shift (`name`/`date`/`shift_type`) |

A ready-to-use **agent prompt** that drives these (inspect → pick the canonical
tab → ingest → report) is in [`AGENT_PROMPT.md`](AGENT_PROMPT.md).

Point an MCP client at it with an `Authorization: Bearer <token>` header. Quick
check with curl:

```bash
curl -s https://scheduler.calvingunther.com/claude-mcp \
  -H "Authorization: Bearer sk_sched_…" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ingest_latest"}}'
```

Set up a recurring Claude session that calls `list_spreadsheets` then
`ingest_latest` daily/weekly — it can inspect results and decide what to do.

### b) Plain REST (cron + curl)
```bash
# /etc/cron.d/schedule-ingest  — every day at 6am
0 6 * * *  curl -fsS -X POST https://scheduler.calvingunther.com/api/automation/ingest-latest \
             -H "Authorization: Bearer sk_sched_…"
```

### c) Built-in scheduler (no external agent)
Set `AUTO_INGEST` to `daily`, `weekly`, or a number of seconds. The server then
ingests the latest from the inbox on that interval by itself (logged as
`scheduler`). Default `off`.

## Security model

- Tokens are random (`sk_sched_…`), stored only as SHA-256 hashes, scope-limited to
  their capabilities, and revocable. The secret is shown once.
- The MCP endpoint and automation routes **require the `automate` capability** —
  a leaked low-scope token can't ingest, and a non-automate token is rejected.
- Everything is **audit-logged** (`token_create`, `token_revoke`, `auto_ingest`,
  `mcp_tool`) and visible in the Activity tab.
- All traffic is HTTPS via the Cloudflare tunnel; no extra ports are opened.
- Revoke a token and the agent instantly loses access; rotate by minting a new one.

## Where it lives in code

| Concern | Code |
|---------|------|
| API tokens (hash, verify, revoke) | `server/apitokens.py` |
| Inbox scan + idempotent ingest | `server/automation.py` |
| MCP JSON-RPC server | `server/mcp.py` + `/claude-mcp` in `server/app.py` |
| Built-in scheduler | `server/app.py` (`AUTO_INGEST`) |
