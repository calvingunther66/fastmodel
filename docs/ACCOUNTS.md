# Accounts, roles & self-service

The app uses real per-person accounts (not a shared password). Everything lives
in `DATA_DIR` (the Docker volume), so accounts and history survive rebuilds.

## The bootstrap admin

One admin always exists, defined by environment variables:

```
APP_USERNAME=you
APP_PASSWORD=a-strong-password
```

On every startup this account is (re)created and its password is re-synced from
the env vars — so you can **never lock yourself out**. It is marked `protected`:
it can't be deleted or demoted, and you change its password by changing
`APP_PASSWORD` (not in the UI).

> To rotate any *other* account's password you forgot, an admin resets it from
> the **Users** screen.

## Roles & capabilities

| Role | Can do |
|------|--------|
| **admin** | everything (all capabilities implicitly) |
| **member** | self-service, plus any capabilities an admin grants |

Capabilities an admin can toggle per member (delegation) — one by one, or in
small groups via the one-click **presets**:

| Capability | Grants |
|------------|--------|
| `upload` | upload / re-parse schedules |
| `generate_schedule` | the assisted generator + builder templates (Create tab) |
| `manage_roster` | edit the staff roster (clinics, nights, employment) — Roster tab |
| `manage_coverage` | mark anyone out, assign covers, run cascades, approve claims, edit any contact |
| `manage_swaps` | approve member shift swaps |
| `manage_users` | create / edit / delete accounts + mint API tokens |
| `view_leaderboard` | see the step-up / equity dashboard (Insights tab) |
| `tune_scoring` | adjust the fairness-vs-competence scoring dial |
| `export` | download CSV / printable schedule exports |
| `automate` | use the automation API + `/claude-mcp` endpoint |

Each is independent (e.g. `view_leaderboard` and `tune_scoring` can be granted
separately). **Presets** in the Users screen select a small group at once:
*Coordinator* (`manage_coverage` + `manage_swaps`), *Scheduler* (`upload` +
`generate_schedule` + `manage_roster`), *Analyst* (`view_leaderboard` +
`tune_scoring` + `export`), *Automation* (`automate`). The live list comes from
`GET /api/capabilities`.

A member with, say, `manage_coverage` becomes a coverage coordinator without
being a full admin.

## Linking an account to a person

Each account can be linked to a **schedule name** (e.g. `GUNTHER`). The link
powers self-service and defaults their "My calendar" to themselves. Set it when
creating the account or later from the Users screen.

## What a member can do

- **View** the full team schedule and everyone's calendar links.
- **Call out** of their own assigned shifts ("can't work") — this flags the
  shift open (and feeds the coverage tools), and they can undo it.
- **Offer days they can cover** — they then surface as a ranked candidate
  (with an "offered to cover this day" reason) when someone calls out.
- **Edit their own contact info** (cell/pager), which admins see for coverage calls.

Admins (or anyone with `manage_coverage`) can do all of the above for anyone, plus
the full Coverage workflow (proposals, assign, cascades).

## Account security (F1/F2/F3)

All standard-library — no extra dependencies.

- **Login lockout (F1).** Repeated failed logins for a username are throttled
  in-memory: after `LOGIN_MAX_ATTEMPTS` (default 5) the account is locked for
  `LOGIN_LOCKOUT_SECONDS` (default 900s), and `/api/login` returns `429` with a
  `Retry-After` header. A successful login (or the lapse of the window) clears it.
  The counter is per-process, so a restart resets it (fine for the single-container
  Pi deploy). Tune via env vars.
- **Two-factor auth (F2, TOTP).** Any user can turn on TOTP from the **Security**
  tab: it shows a secret + `otpauth://` URI to add to an authenticator app, then
  asks for a 6-digit code to confirm (so a half-finished enrolment can't lock you
  out). Once enabled, login requires the current code — the API responds
  `401 {"detail":"otp_required"}` to prompt for it, then verifies it (±1 time-step
  for clock drift). Turning 2FA off requires the account password. Admins are
  encouraged to enable it. Secrets live in `users.json`; `public_view` only exposes
  `totp_enabled`, never the secret.
- **Password reset codes (F3).** No email channel, so reset is admin-mediated: an
  admin clicks **reset code** on the Users screen to mint a one-time code (valid 24h),
  hands it to the member privately, and the member redeems it from the **“Have a
  reset code?”** link on the sign-in screen to choose a new password. The code is
  stored hashed (PBKDF2) with an expiry and is single-use. Admins can still set a
  password directly via the **password** button.

## Where it lives in code

| Concern | Code |
|---------|------|
| Accounts, hashing, roles/caps | `server/accounts.py` (`AccountStore`, `hash_password`, `has_cap`) |
| Login throttle + TOTP helpers | `server/security.py` (`LoginThrottle`, `verify_totp`) |
| Auth + capability gating | `server/app.py` (`require_auth`, `require_cap`) |
| Offers / contacts / call-outs | `server/store.py` (+ `server/coverage.py` for proposals) |
| Account UI | `web/src/components/Users.jsx` |
| 2FA / reset UI | `web/src/components/Security.jsx`, `web/src/components/Login.jsx` |
| Self-service UI | `web/src/components/MyAvailability.jsx` |

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library). Session cookies
are signed with `SECRET_KEY`, which is persisted in `DATA_DIR/secret_key` when not
set via env, so sessions survive restarts.
