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

Capabilities an admin can toggle per member (delegation):

| Capability | Grants |
|------------|--------|
| `upload` | upload / re-parse schedules |
| `manage_coverage` | mark anyone out, assign covers, run cascades, edit any contact |
| `manage_users` | create / edit / delete accounts |

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

## Where it lives in code

| Concern | Code |
|---------|------|
| Accounts, hashing, roles/caps | `server/accounts.py` (`AccountStore`, `hash_password`, `has_cap`) |
| Auth + capability gating | `server/app.py` (`require_auth`, `require_cap`) |
| Offers / contacts / call-outs | `server/store.py` (+ `server/coverage.py` for proposals) |
| Account UI | `web/src/components/Users.jsx` |
| Self-service UI | `web/src/components/MyAvailability.jsx` |

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library). Session cookies
are signed with `SECRET_KEY`, which is persisted in `DATA_DIR/secret_key` when not
set via env, so sessions survive restarts.
