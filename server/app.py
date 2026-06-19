"""FastAPI app: accounts + roles, schedule viewer, self-service, .ics feeds.

Auth model
  - One bootstrap admin from env (APP_USERNAME/APP_PASSWORD), always valid.
  - Admins create accounts and delegate capabilities (upload, manage_coverage,
    manage_users). Members are self-service.
  - Session cookie carries the username; all accounts/data persist in DATA_DIR.

Members can: view the team schedule + calendar links, call out of their own
shifts, offer days they can cover, and edit their own contact info.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import config, mcp
from .accounts import CAPABILITIES, CAPABILITY_PRESETS, AccountStore, has_cap, public_view
from .apitokens import ApiTokenStore
from .audit import AuditLog
from .automation import Automation
from .coverage import propose as propose_coverage
from .generator import generate as generate_schedule_draft
from .ical import build_ics
from .roster import StaffRoster
from .security import LoginThrottle
from .store import ScheduleStore
from .validate import summarize, validate_schedule

app = FastAPI(title="fastmodel schedule")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    same_site="lax",
    https_only=config.SESSION_HTTPS_ONLY,
)

store = ScheduleStore()
accounts = AccountStore()
audit = AuditLog()
roster = StaffRoster()
api_tokens = ApiTokenStore()
automation = Automation(store)
login_throttle = LoginThrottle(
    max_attempts=config.LOGIN_MAX_ATTEMPTS,
    lockout_seconds=config.LOGIN_LOCKOUT_SECONDS,
)
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def require_oversight(request: Request) -> dict:
    """Admins, or members granted manage_users / manage_coverage, may view activity."""
    user = require_auth(request)
    if user.get("role") == "admin" or has_cap(user, "manage_users") or has_cap(user, "manage_coverage"):
        return user
    raise HTTPException(status_code=403, detail="not permitted")


# --------------------------------------------------------------------------
# auth helpers
# --------------------------------------------------------------------------
class Credentials(BaseModel):
    username: str
    password: str
    otp: str | None = None


def current_user(request: Request) -> dict | None:
    # An API bearer token authenticates as a scoped service principal.
    authz = request.headers.get("Authorization", "")
    if authz.startswith("Bearer "):
        return api_tokens.verify(authz[7:].strip())
    uname = request.session.get("user")
    return accounts.get(uname) if uname else None


def require_auth(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_cap(cap: str):
    def dep(request: Request) -> dict:
        user = require_auth(request)
        if not has_cap(user, cap):
            raise HTTPException(status_code=403, detail=f"requires '{cap}' permission")
        return user
    return dep


def _own_person(user: dict) -> str:
    person = user.get("person")
    if not person:
        raise HTTPException(
            status_code=400,
            detail="your account isn't linked to a schedule name; ask an admin",
        )
    return person


@app.post("/api/login")
def login(creds: Credentials, request: Request):
    key = (creds.username or "").strip().lower()

    # F1: refuse while the account is locked out from repeated failures.
    retry = login_throttle.retry_after(key)
    if retry:
        audit.log(creds.username, "login_locked", {"retry_after": retry})
        raise HTTPException(
            status_code=429,
            detail=f"too many attempts — try again in {retry // 60 + 1} min",
            headers={"Retry-After": str(retry)},
        )

    user = accounts.authenticate(creds.username, creds.password)
    if not user:
        locked = login_throttle.record_failure(key)
        audit.log(creds.username, "login_failed", {"locked": bool(locked)})
        raise HTTPException(status_code=401, detail="invalid credentials")

    # F2: if the account has TOTP enabled, require a valid one-time code.
    if user.get("totp_enabled"):
        if not creds.otp:
            # Prompt for the code without counting it as a failed attempt.
            raise HTTPException(status_code=401, detail="otp_required")
        if not accounts.verify_totp_code(user, creds.otp):
            login_throttle.record_failure(key)
            audit.log(user["username"], "login_failed", {"reason": "bad_otp"})
            raise HTTPException(status_code=401, detail="invalid authentication code")

    login_throttle.reset(key)
    request.session["user"] = user["username"]
    audit.log(user["username"], "login")
    return {"authenticated": True, "user": public_view(user)}


@app.post("/api/reset-password")
def reset_password(payload: dict):
    """Redeem an admin-issued one-time reset code (F3). No auth — the code is
    the secret. Always returns the same error for bad username/code/expiry."""
    username = (payload.get("username") or "").strip()
    code = payload.get("code") or ""
    new_password = payload.get("new_password") or ""
    try:
        accounts.redeem_reset(username, code, new_password)
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="invalid or expired reset code")
    login_throttle.reset(username.lower())
    audit.log(username, "password_reset_redeemed")
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": public_view(user)}


# ---- two-factor auth, self-service (F2) ----------------------------------
@app.post("/api/me/2fa/begin")
def begin_2fa(request: Request, user: dict = Depends(require_auth)):
    """Start TOTP enrollment: returns a secret + otpauth URI to add to an app.
    Not active until confirmed via /enable with a valid code."""
    info = accounts.begin_totp(user["username"])
    audit.log(user["username"], "2fa_enroll_begin")
    return info


@app.post("/api/me/2fa/enable")
def enable_2fa(payload: dict, request: Request, user: dict = Depends(require_auth)):
    try:
        accounts.enable_totp(user["username"], payload.get("otp", ""))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "2fa_enabled")
    return {"ok": True, "totp_enabled": True}


@app.post("/api/me/2fa/disable")
def disable_2fa(payload: dict, request: Request, user: dict = Depends(require_auth)):
    """Turn off 2FA. Requires the current password (defence in depth)."""
    if not accounts.authenticate(user["username"], payload.get("password", "")):
        raise HTTPException(status_code=403, detail="current password required")
    accounts.disable_totp(user["username"])
    audit.log(user["username"], "2fa_disabled")
    return {"ok": True, "totp_enabled": False}


# --------------------------------------------------------------------------
# schedule (any signed-in user may view the team)
# --------------------------------------------------------------------------
@app.get("/api/schedule")
def get_schedule(user: dict = Depends(require_auth)):
    schedule = store.get_schedule()
    if schedule is None:
        return JSONResponse({"empty": True})
    return schedule


def _ics_base(request: Request) -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


@app.get("/api/people")
def people(request: Request, user: dict = Depends(require_auth)):
    base = _ics_base(request)
    out = []
    for p in store.people_with_tokens():
        url = f"{base}/calendar/{p['token']}.ics"
        out.append({
            "name": p["name"],
            "shift_count": p["shift_count"],
            "ics_url": url,
            "webcal_url": url.replace("http://", "webcal://").replace("https://", "webcal://"),
        })
    return out


# --------------------------------------------------------------------------
# upload (requires the 'upload' capability)
# --------------------------------------------------------------------------
@app.post("/api/schedule/upload")
async def upload(
    file: UploadFile,
    sheet: str | None = Form(default=None),
    user: dict = Depends(require_cap("upload")),
):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="please upload an .xlsx file")
    data = await file.read()
    try:
        result = store.ingest(data, sheet_name=sheet)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not parse: {exc}")
    audit.log(user["username"], "upload_schedule",
              {"sheet": result.get("parsed_sheet"), "file": file.filename})
    return {
        "parsed_sheet": result.get("parsed_sheet"),
        "available_sheets": result.get("available_sheets", []),
        "people": len([p for p in result.get("people", []) if p.get("name")]),
    }


@app.get("/api/roster")
def get_roster(user: dict = Depends(require_auth)):
    return {"staff": roster.list(), "placeholder": roster.is_placeholder()}


@app.post("/api/roster")
def set_roster(payload: dict, user: dict = Depends(require_cap("manage_roster"))):
    staff = payload.get("staff")
    if not isinstance(staff, list):
        raise HTTPException(status_code=400, detail="staff must be a list")
    saved = roster.replace(staff)
    audit.log(user["username"], "roster_update", {"people": len(saved)})
    return {"staff": saved, "placeholder": roster.is_placeholder()}


@app.get("/api/codes")
def get_codes(user: dict = Depends(require_auth)):
    from schedule_extractor.definitions import CLINICS, LOCATIONS, STATUS
    return {"locations": LOCATIONS, "statuses": STATUS, "clinics": sorted(CLINICS)}


@app.post("/api/schedule/create")
def create_schedule(payload: dict, user: dict = Depends(require_cap("upload"))):
    title = (payload.get("title") or "New schedule").strip()
    start, end = payload.get("start"), payload.get("end")
    if not (start and end):
        raise HTTPException(status_code=400, detail="start and end dates are required")
    result = store.create_schedule(title, start, end, payload.get("assignments") or {})
    audit.log(user["username"], "create_schedule",
              {"title": title, "people": len([p for p in result["people"] if p["shifts"]])})
    return {"title": title,
            "people": len([p for p in result["people"] if p["shifts"]])}


@app.get("/api/capabilities")
def list_capabilities(user: dict = Depends(require_auth)):
    """The delegatable capabilities and the one-click presets, for the Users UI."""
    return {"capabilities": CAPABILITIES, "presets": CAPABILITY_PRESETS}


@app.get("/api/vacations")
def list_vacations(user: dict = Depends(require_auth)):
    """Vacation (V) entries in the active schedule with effective approval (H1)."""
    return store.list_vacations()


@app.post("/api/vacations/decide")
def decide_vacation(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    person, date = payload.get("person"), payload.get("date")
    status = payload.get("status")
    if not (person and date):
        raise HTTPException(status_code=400, detail="person and date are required")
    try:
        result = store.set_vacation(person, date, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "decide_vacation",
              {"person": person, "date": date, "status": status})
    return result


@app.get("/api/coverage/forecast")
def coverage_forecast(user: dict = Depends(require_cap("manage_coverage"))):
    """Upcoming coverage gaps / single-points-of-failure (K2)."""
    from .forecast import forecast as run_forecast
    schedule = store.get_schedule() or {"people": []}
    return run_forecast(schedule, roster=roster.engine_quals())


@app.get("/api/holidays")
def list_holidays(user: dict = Depends(require_auth)):
    return store.list_holidays()


@app.post("/api/holidays")
def add_holiday(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    date = payload.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    try:
        result = store.add_holiday(date, payload.get("label", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "add_holiday", result)
    return result


@app.delete("/api/holidays/{date}")
def remove_holiday(date: str, user: dict = Depends(require_cap("manage_coverage"))):
    store.remove_holiday(date)
    audit.log(user["username"], "remove_holiday", {"date": date})
    return {"ok": True}


@app.get("/api/schedule/issues")
def schedule_issues(user: dict = Depends(require_auth)):
    """Validator/linter results for the active schedule (A2/A3)."""
    schedule = store.get_schedule()
    if not schedule:
        return {"issues": [], "summary": summarize([])}
    issues = validate_schedule(schedule, roster=roster.engine_quals(),
                               prefs=store.list_prefs())
    return {"issues": issues, "summary": summarize(issues)}


@app.post("/api/schedule/generate")
def schedule_generate(payload: dict, user: dict = Depends(require_cap("generate_schedule"))):
    """Draft a schedule (does not persist) — the admin edits it in Create then saves."""
    start, end = payload.get("start"), payload.get("end")
    if not (start and end):
        raise HTTPException(status_code=400, detail="start and end dates are required")
    quals = roster.quals()  # generator needs quals; placeholder is fine for a draft
    if not quals:
        raise HTTPException(status_code=400, detail="no staff roster to generate from")
    draft = generate_schedule_draft(start, end, quals, prefs=store.list_prefs(),
                                    stats=store.aggregated_stats(),
                                    unavailable=store.approved_vacations(),
                                    debt=store.fairness_debt())
    audit.log(user["username"], "generate_draft",
              {"start": start, "end": end, "people": draft["report"]["people"]})
    return draft


@app.post("/api/schedule/reparse")
def reparse(payload: dict, user: dict = Depends(require_cap("upload"))):
    sheet = payload.get("sheet")
    if not sheet:
        raise HTTPException(status_code=400, detail="sheet is required")
    try:
        result = store.reparse(sheet)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="no workbook uploaded yet")
    return {"parsed_sheet": result.get("parsed_sheet")}


# --------------------------------------------------------------------------
# coverage (requires 'manage_coverage'; members self-serve via /api/me/*)
# --------------------------------------------------------------------------
def _coverage_target(payload: dict):
    name, date, shift_type = payload.get("name"), payload.get("date"), payload.get("shift_type")
    if not (name and date and shift_type):
        raise HTTPException(status_code=400, detail="name, date and shift_type are required")
    return name, date, shift_type


def _propose(name, date, shift_type):
    schedule = store.get_schedule() or {"people": []}
    return propose_coverage(schedule, name, date, shift_type,
                            offered=store.offers_for_date(date),
                            stats=store.aggregated_stats(),
                            fairness_weight=store.get_fairness_weight(),
                            roster=roster.engine_quals())


@app.get("/api/coverage/callouts")
def list_callouts(user: dict = Depends(require_auth)):
    return store.list_callouts()


@app.get("/api/coverage/stats")
def coverage_stats(user: dict = Depends(require_oversight)):
    return store.aggregated_stats()


@app.get("/api/coverage/leaderboard")
def coverage_leaderboard(user: dict = Depends(require_cap("view_leaderboard"))):
    return store.leaderboard()


@app.get("/api/coverage/settings")
def coverage_settings(user: dict = Depends(require_auth)):
    return {"fairness_weight": store.get_fairness_weight()}


@app.post("/api/coverage/settings")
def set_coverage_settings(payload: dict, user: dict = Depends(require_cap("tune_scoring"))):
    if "fairness_weight" not in payload:
        raise HTTPException(status_code=400, detail="fairness_weight is required")
    try:
        w = store.set_fairness_weight(payload["fairness_weight"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="fairness_weight must be 0..1")
    audit.log(user["username"], "tune_scoring", {"fairness_weight": w})
    return {"fairness_weight": w}


@app.post("/api/coverage/propose")
def coverage_propose(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    return _propose(*_coverage_target(payload))


@app.post("/api/coverage/sick")
def coverage_sick(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    store.mark_sick(name, date, shift_type, code=payload.get("code"),
                    reason=payload.get("reason", "out sick"))
    audit.log(user["username"], "mark_sick", {"name": name, "date": date, "shift": shift_type})
    return _propose(name, date, shift_type)


@app.post("/api/coverage/assign")
def coverage_assign(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    covered_by = payload.get("covered_by")
    if not covered_by:
        raise HTTPException(status_code=400, detail="covered_by is required")
    store.assign_cover(name, date, shift_type, covered_by)
    audit.log(user["username"], "assign_cover",
              {"name": name, "date": date, "shift": shift_type, "covered_by": covered_by})
    return {"ok": True, "covered_by": covered_by}


@app.post("/api/coverage/assign-cascade")
def coverage_assign_cascade(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    mover, backfill = payload.get("mover"), payload.get("backfill")
    frm = payload.get("from") or {}
    if not (mover and backfill and frm.get("shift_type")):
        raise HTTPException(status_code=400, detail="mover, backfill and from are required")
    store.assign_cascade(name, date, shift_type, mover,
                         frm.get("code"), frm["shift_type"], backfill)
    audit.log(user["username"], "assign_cascade",
              {"name": name, "date": date, "shift": shift_type,
               "mover": mover, "backfill": backfill})
    return {"ok": True, "mover": mover, "backfill": backfill}


@app.post("/api/coverage/apply-chain")
def coverage_apply_chain(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    """Apply a multi-step (3+) cascade chain (I2)."""
    name, date, shift_type = _coverage_target(payload)
    steps, backfill = payload.get("steps"), payload.get("backfill")
    if not steps or not backfill:
        raise HTTPException(status_code=400, detail="steps and backfill are required")
    store.apply_chain(name, date, shift_type, steps, backfill)
    audit.log(user["username"], "apply_chain",
              {"name": name, "date": date, "shift": shift_type,
               "depth": len(steps), "backfill": backfill})
    return {"ok": True}


@app.post("/api/coverage/clear")
def coverage_clear(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    store.clear_callout(name, date, shift_type)
    audit.log(user["username"], "clear_callout", {"name": name, "date": date, "shift": shift_type})
    return {"ok": True}


@app.post("/api/coverage/unassign")
def coverage_unassign(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    """Undo a cover assignment: the shift reopens, the call-out stays (I1)."""
    name, date, shift_type = _coverage_target(payload)
    undone = store.unassign_cover(name, date, shift_type)
    audit.log(user["username"], "unassign_cover",
              {"name": name, "date": date, "shift": shift_type, "undone": undone})
    return {"ok": True, "reopened": undone}


# --------------------------------------------------------------------------
# self-service (members, scoped to their own linked person)
# --------------------------------------------------------------------------
@app.post("/api/me/callout")
def my_callout(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    date, shift_type = payload.get("date"), payload.get("shift_type")
    if not (date and shift_type):
        raise HTTPException(status_code=400, detail="date and shift_type are required")
    store.mark_sick(person, date, shift_type, code=payload.get("code"),
                    reason="out (self-reported)")
    audit.log(user["username"], "self_callout", {"person": person, "date": date, "shift": shift_type})
    return {"ok": True}


@app.post("/api/me/callout/clear")
def my_callout_clear(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    date, shift_type = payload.get("date"), payload.get("shift_type")
    if not (date and shift_type):
        raise HTTPException(status_code=400, detail="date and shift_type are required")
    store.clear_callout(person, date, shift_type)
    return {"ok": True}


def _describe_change(person: str, entry: dict) -> str:
    """A first-person sentence for a personal-feed entry (J1)."""
    d = entry.get("details") or {}
    a, action = entry.get("actor"), entry.get("action")
    date, shift = d.get("date"), d.get("shift")
    when = f" on {date}" if date else ""
    sh = f" {shift}" if shift else ""
    me = person.lower()

    def is_me(key):
        return str(d.get(key, "")).strip().lower() == me

    if action == "assign_cover":
        if is_me("name"):
            return f"Your{sh} shift{when} is now covered by {d.get('covered_by')}."
        if is_me("covered_by"):
            return f"You were assigned to cover {d.get('name')}'s{sh} shift{when}."
    if action == "unassign_cover" and is_me("name"):
        return f"Cover for your{sh} shift{when} was undone — it's open again."
    if action in ("mark_sick", "self_callout") and (is_me("name") or is_me("person")):
        return f"You were marked out{sh}{when}."
    if action == "clear_callout" and is_me("name"):
        return f"Your call-out{sh}{when} was cleared."
    if action == "decide_vacation" and is_me("person"):
        return f"Your vacation{when} was {d.get('status', 'updated')}."
    if action == "approve_claim" and is_me("claimer"):
        return f"Your offer to cover {d.get('name')}'s{sh} shift{when} was approved."
    if action == "decide_swap" and (is_me("a_person") or is_me("b_person")):
        return f"A swap involving you was {d.get('decision', 'updated')}."
    if action == "propose_swap" and is_me("with"):
        return f"{a} proposed a shift swap with you."
    if action in ("apply_chain", "assign_cascade") and (is_me("mover") or is_me("backfill")):
        return f"You were moved to help cover a shift{when}."
    # generic fallback
    return f"{action.replace('_', ' ')}{when}."


@app.get("/api/me/changes")
def my_changes(user: dict = Depends(require_auth)):
    """A personal 'what changed for me' feed (J1), newest first."""
    person = _own_person(user)
    entries = audit.for_person(person)
    return [{"ts": e["ts"], "action": e["action"],
             "summary": _describe_change(person, e)} for e in entries]


@app.get("/api/availability")
def availability(user: dict = Depends(require_auth)):
    return store.list_offers()


@app.post("/api/me/offer")
def my_offer(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    date = payload.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    store.add_offer(person, date, note=payload.get("note", ""))
    audit.log(user["username"], "offer_cover", {"person": person, "date": date})
    return {"ok": True}


@app.post("/api/me/offer/remove")
def my_offer_remove(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    date = payload.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    store.remove_offer(person, date)
    return {"ok": True}


@app.post("/api/me/contact")
def my_contact(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    contact = payload.get("contact")
    if not isinstance(contact, list):
        raise HTTPException(status_code=400, detail="contact must be a list of lines")
    store.set_contact(person, contact)
    audit.log(user["username"], "edit_contact", {"person": person})
    return {"ok": True}


@app.post("/api/contact")
def set_contact(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    person, contact = payload.get("person"), payload.get("contact")
    if not person or not isinstance(contact, list):
        raise HTTPException(status_code=400, detail="person and contact[] are required")
    store.set_contact(person, contact)
    return {"ok": True}


# ---- member preferences (B4) ---------------------------------------------
@app.get("/api/me/prefs")
def get_my_prefs(user: dict = Depends(require_auth)):
    return store.get_prefs(_own_person(user))


@app.post("/api/me/prefs")
def set_my_prefs(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    saved = store.set_prefs(person, payload or {})
    audit.log(user["username"], "set_prefs", {"person": person})
    return saved


# ---- open shifts + claims (B1) -------------------------------------------
def _eligible_to_cover(person: str, co: dict) -> tuple[bool, str]:
    """Is `person` plausibly able to cover this open call-out? (roster-aware)."""
    quals = roster.engine_quals()
    code = (co.get("code") or "").upper()
    if quals is not None:
        meta = quals.get(person.upper())
        if meta is None:
            return False, "not on the roster"
        if co["shift_type"] == "night" and not meta.get("works_nights", True):
            return False, "doesn’t work nights"
        if meta.get("clinics") and code and code not in meta["clinics"]:
            return False, f"not qualified for {code}"
    return True, "eligible"


@app.get("/api/open-shifts")
def open_shifts(user: dict = Depends(require_auth)):
    """Call-outs that still need a cover, with this user's eligibility + claim state.

    Each row carries days_until the shift and an urgency band (I3); the list is
    sorted soonest-first so imminent uncovered shifts surface at the top."""
    import datetime as _dt
    person = user.get("person")
    today = _dt.date.today()
    out = []
    for co in store.list_callouts():
        if co.get("covered_by"):
            continue
        try:
            days_until = (_dt.date.fromisoformat(co["date"]) - today).days
        except (ValueError, KeyError, TypeError):
            days_until = None
        urgency = "past" if (days_until is not None and days_until < 0) else (
            "urgent" if (days_until is not None and days_until <= 2) else (
                "soon" if (days_until is not None and days_until <= 6) else "later"))
        row = {"name": co["name"], "date": co["date"], "shift_type": co["shift_type"],
               "code": co.get("code"), "reason": co.get("reason"),
               "created_at": co.get("created_at"),
               "days_until": days_until, "urgency": urgency,
               "claimers": store.claims_for(co["name"], co["date"], co["shift_type"])}
        if person:
            ok, why = _eligible_to_cover(person, co)
            row["eligible"] = ok and person != co["name"]
            row["eligibility"] = why
            row["claimed_by_me"] = person in row["claimers"]
        out.append(row)
    out.sort(key=lambda r: (r["days_until"] if r["days_until"] is not None else 9999,
                            r["name"]))
    return out


@app.post("/api/me/claim")
def claim_open_shift(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    name, date, shift_type = _coverage_target(payload)
    store.add_claim(person, name, date, shift_type)
    audit.log(user["username"], "claim_shift",
              {"claimer": person, "name": name, "date": date, "shift": shift_type})
    return {"ok": True}


@app.post("/api/me/claim/remove")
def unclaim_open_shift(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    name, date, shift_type = _coverage_target(payload)
    store.remove_claim(person, name, date, shift_type)
    return {"ok": True}


@app.post("/api/coverage/approve-claim")
def approve_claim(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    claimer = payload.get("claimer")
    if not claimer:
        raise HTTPException(status_code=400, detail="claimer is required")
    store.assign_cover(name, date, shift_type, claimer)
    store.remove_claim(claimer, name, date, shift_type)
    audit.log(user["username"], "approve_claim",
              {"name": name, "date": date, "shift": shift_type, "claimer": claimer})
    return {"ok": True, "covered_by": claimer}


# ---- what-if simulator (C2) ----------------------------------------------
@app.post("/api/coverage/simulate")
def simulate(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    """Preview the impact of marking someone out, without persisting anything."""
    name, date, shift_type = _coverage_target(payload)
    proposal = _propose(name, date, shift_type)
    issues = validate_schedule(store.get_schedule() or {}, roster=roster.engine_quals(),
                               prefs=store.list_prefs())
    return {"proposal": proposal, "issues": issues, "summary": summarize(issues)}


# ---- shift swaps (B3) -----------------------------------------------------
@app.get("/api/swaps")
def list_swaps(user: dict = Depends(require_auth)):
    return store.list_swaps()


@app.post("/api/me/swap")
def propose_swap(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    need = ("a_date", "a_type", "b_person", "b_date", "b_type")
    if not all(payload.get(k) for k in need):
        raise HTTPException(status_code=400, detail=f"required: {', '.join(need)}")
    sw = store.propose_swap(person, payload["a_date"], payload["a_type"],
                            payload["b_person"], payload["b_date"], payload["b_type"])
    audit.log(user["username"], "propose_swap", {"id": sw["id"], "with": payload["b_person"]})
    return sw


@app.post("/api/me/swap/accept")
def accept_swap(payload: dict, user: dict = Depends(require_auth)):
    person = _own_person(user)
    sw = store.list_swaps()
    target = next((s for s in sw if s["id"] == payload.get("id")), None)
    if not target:
        raise HTTPException(status_code=404, detail="no such swap")
    if target["b_person"] != person:
        raise HTTPException(status_code=403, detail="only the other party can accept")
    updated = store.set_swap_status(target["id"], "accepted")
    audit.log(user["username"], "accept_swap", {"id": target["id"]})
    return updated


@app.post("/api/swaps/decide")
def decide_swap(payload: dict, user: dict = Depends(require_cap("manage_swaps"))):
    swap_id, decision = payload.get("id"), payload.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be approved|rejected")
    updated = store.set_swap_status(swap_id, decision)
    if not updated:
        raise HTTPException(status_code=404, detail="no such swap")
    audit.log(user["username"], "decide_swap", {"id": swap_id, "decision": decision})
    return updated


# ---- builder templates (C3) ----------------------------------------------
@app.get("/api/templates")
def list_templates(user: dict = Depends(require_cap("generate_schedule"))):
    return store.list_templates()


@app.post("/api/templates")
def save_template(payload: dict, user: dict = Depends(require_cap("generate_schedule"))):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return store.save_template(name, payload.get("weekday_levels") or {})


@app.delete("/api/templates/{name}")
def delete_template(name: str, user: dict = Depends(require_cap("generate_schedule"))):
    store.delete_template(name)
    return {"ok": True}


# ---- exports (D2) ---------------------------------------------------------
@app.get("/api/export/schedule.csv")
def export_schedule_csv(user: dict = Depends(require_cap("export"))):
    from .exports import schedule_csv
    csv_text = schedule_csv(store.get_schedule() or {})
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="schedule.csv"'})


@app.get("/api/export/person/{name}.csv")
def export_person_csv(name: str, user: dict = Depends(require_auth)):
    from .exports import person_csv
    csv_text = person_csv(store.get_schedule() or {}, name)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="no such person")
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


# --------------------------------------------------------------------------
# user management (requires 'manage_users')
# --------------------------------------------------------------------------
@app.get("/api/users")
def list_users(user: dict = Depends(require_cap("manage_users"))):
    return [public_view(u) for u in accounts.list()]


@app.post("/api/users")
def create_user(payload: dict, user: dict = Depends(require_cap("manage_users"))):
    try:
        created = accounts.create(
            payload.get("username", ""), payload.get("password", ""),
            role=payload.get("role", "member"), person=payload.get("person"),
            capabilities=payload.get("capabilities") or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "user_create",
              {"username": created["username"], "role": created["role"]})
    return public_view(created)


@app.patch("/api/users/{username}")
def update_user(username: str, payload: dict, user: dict = Depends(require_cap("manage_users"))):
    try:
        updated = accounts.update(
            username,
            role=payload.get("role"),
            person=payload["person"] if "person" in payload else ...,
            capabilities=payload.get("capabilities"),
            password=payload.get("password"),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="no such user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "user_update",
              {"username": username, "fields": [k for k in payload if k != "password"],
               "password_reset": bool(payload.get("password"))})
    return public_view(updated)


@app.post("/api/users/{username}/reset-code")
def issue_reset_code(username: str, user: dict = Depends(require_cap("manage_users"))):
    """Mint a one-time reset code to hand to a member (F3). Shown once."""
    try:
        code = accounts.issue_reset_code(username)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such user")
    audit.log(user["username"], "issue_reset_code", {"username": username})
    return {"username": username, "code": code, "expires_hours": 24}


@app.delete("/api/users/{username}")
def delete_user(username: str, user: dict = Depends(require_cap("manage_users"))):
    try:
        accounts.delete(username)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "user_delete", {"username": username})
    return {"ok": True}


# --------------------------------------------------------------------------
# activity log (admins / oversight)
# --------------------------------------------------------------------------
@app.get("/api/audit")
def get_audit(limit: int = 200, user: dict = Depends(require_oversight)):
    return audit.tail(min(max(limit, 1), 1000))


# --------------------------------------------------------------------------
# API tokens for automation (manage_users mints; tokens carry their own scope)
# --------------------------------------------------------------------------
@app.get("/api/tokens")
def list_tokens(user: dict = Depends(require_cap("manage_users"))):
    return api_tokens.list()


@app.post("/api/tokens")
def create_token(payload: dict, user: dict = Depends(require_cap("manage_users"))):
    name = payload.get("name", "agent")
    caps = payload.get("capabilities") or ["automate"]
    record, secret = api_tokens.create(name, caps)
    audit.log(user["username"], "token_create", {"name": record["name"], "caps": record["capabilities"]})
    # The secret is returned exactly once.
    return {**record, "token": secret}


@app.delete("/api/tokens/{token_id}")
def revoke_token(token_id: str, user: dict = Depends(require_cap("manage_users"))):
    api_tokens.revoke(token_id)
    audit.log(user["username"], "token_revoke", {"id": token_id})
    return {"ok": True}


# --------------------------------------------------------------------------
# backup & restore of the whole data directory (L1)
# --------------------------------------------------------------------------
@app.get("/api/backup")
def download_backup(user: dict = Depends(require_cap("manage_users"))):
    from .backup import backup_filename, make_backup
    data = make_backup(config.DATA_DIR)
    audit.log(user["username"], "backup_download", {"bytes": len(data)})
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{backup_filename()}"'})


@app.post("/api/restore")
async def upload_restore(file: UploadFile, user: dict = Depends(require_cap("manage_users"))):
    from .backup import restore_backup
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="please upload a .zip backup")
    data = await file.read()
    try:
        result = restore_backup(config.DATA_DIR, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.log(user["username"], "backup_restore", result)
    return {**result, "note": "restart the app to fully apply restored accounts/keys"}


# --------------------------------------------------------------------------
# automation: watch an inbox of spreadsheets and ingest the latest
# --------------------------------------------------------------------------
@app.get("/api/automation/status")
def automation_status(user: dict = Depends(require_cap("automate"))):
    return automation.status()


@app.get("/api/automation/spreadsheets")
def automation_spreadsheets(user: dict = Depends(require_cap("automate"))):
    return automation.list_spreadsheets()


@app.post("/api/automation/ingest-latest")
def automation_ingest_latest(payload: dict | None = None,
                             user: dict = Depends(require_cap("automate"))):
    result = automation.ingest_latest(sheet=(payload or {}).get("sheet"),
                                      actor=user["username"])
    audit.log(user["username"], "auto_ingest", result)
    return result


# --------------------------------------------------------------------------
# MCP endpoint: agent-driven automation over JSON-RPC (bearer 'automate')
# --------------------------------------------------------------------------
@app.post("/claude-mcp")
async def claude_mcp(request: Request):
    user = current_user(request)
    if not user or not has_cap(user, "automate"):
        raise HTTPException(status_code=401, detail="bearer token with 'automate' required")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    def _tool_audit(name, args):
        audit.log(user["username"], "mcp_tool", {"tool": name, "args": args})

    def _validate_active():
        schedule = store.get_schedule() or {}
        issues = validate_schedule(schedule, roster=roster.engine_quals(),
                                   prefs=store.list_prefs())
        return {"issues": issues, "summary": summarize(issues),
                "active_sheet": schedule.get("parsed_sheet")}

    services = {"validate": _validate_active, "coverage_plan": _propose}

    def _one(msg):
        return mcp.handle(msg, automation, store, on_tool=_tool_audit, services=services)

    if isinstance(body, list):  # JSON-RPC batch
        responses = [r for r in (_one(m) for m in body) if r is not None]
        return JSONResponse(responses if responses else [], status_code=200)
    response = _one(body)
    if response is None:  # a notification
        return Response(status_code=202)
    return JSONResponse(response)


# --------------------------------------------------------------------------
# health check (no auth) — for uptime monitoring / automated backups (E3)
# --------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    schedule = store.get_raw_schedule()
    return {
        "ok": True,
        "version": config.APP_VERSION,
        "has_schedule": schedule is not None,
        "active_sheet": (schedule or {}).get("parsed_sheet"),
        "uploaded_at": (schedule or {}).get("uploaded_at"),
        "people": len([p for p in (schedule or {}).get("people", []) if p.get("name")]),
    }


# --------------------------------------------------------------------------
# ops dashboard (admins) — config + data + health at a glance (L2)
# --------------------------------------------------------------------------
@app.get("/api/ops")
def ops(user: dict = Depends(require_cap("manage_users"))):
    import os
    schedule = store.get_raw_schedule() or {}
    accts = accounts.list()
    # data-dir size + file inventory
    total = 0
    files = []
    for root, _dirs, names in os.walk(config.DATA_DIR):
        for n in names:
            fp = Path(root) / n
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            total += size
            rel = str(fp.relative_to(config.DATA_DIR))
            if not rel.startswith("inbox/"):
                files.append({"name": rel, "bytes": size})
    files.sort(key=lambda f: -f["bytes"])
    return {
        "version": config.APP_VERSION,
        "config": {
            "timezone": config.TIMEZONE,
            "public_base_url": config.PUBLIC_BASE_URL or None,
            "session_https_only": config.SESSION_HTTPS_ONLY,
            "auto_ingest": config.AUTO_INGEST,
            "login_max_attempts": config.LOGIN_MAX_ATTEMPTS,
            "login_lockout_seconds": config.LOGIN_LOCKOUT_SECONDS,
            "using_default_password": config.USING_DEFAULT_PASSWORD,
            "data_dir": str(config.DATA_DIR),
        },
        "data": {"total_bytes": total, "files": files[:25]},
        "schedule": {
            "active_sheet": schedule.get("parsed_sheet"),
            "uploaded_at": schedule.get("uploaded_at"),
            "people": len([p for p in schedule.get("people", []) if p.get("name")]),
        },
        "accounts": {
            "total": len(accts),
            "admins": len([u for u in accts if u.get("role") == "admin"]),
            "with_2fa": len([u for u in accts if u.get("totp_enabled")]),
        },
        "tokens": len(api_tokens.list()),
        "automation": automation.status(),
    }


# --------------------------------------------------------------------------
# kiosk wall display (J2): no-login, token-protected, auto-refreshing board
# --------------------------------------------------------------------------
@app.get("/api/kiosk-token")
def kiosk_token_info(request: Request, user: dict = Depends(require_cap("manage_users"))):
    token = store.kiosk_token()
    return {"token": token, "url": f"{_ics_base(request)}/kiosk/{token}"}


@app.post("/api/kiosk-token/rotate")
def kiosk_token_rotate(request: Request, user: dict = Depends(require_cap("manage_users"))):
    token = store.rotate_kiosk_token()
    audit.log(user["username"], "kiosk_rotate")
    return {"token": token, "url": f"{_ics_base(request)}/kiosk/{token}"}


def _kiosk_html(board: dict) -> str:
    import datetime as _dt
    from html import escape
    pretty = _dt.date.fromisoformat(board["date"]).strftime("%A, %B %-d")
    labels = [("day", "Day"), ("midshift", "Mid"), ("night", "Night")]
    cols = []
    for key, label in labels:
        rows = board["levels"].get(key, [])
        items = "".join(
            f'<li><b>{escape(r["code"] or "")}</b> {escape(r["name"] or "")}'
            + (f' <span class="cov">↺ {escape(r["covering_for"])}</span>' if r.get("covering_for") else "")
            + "</li>"
            for r in rows) or '<li class="none">—</li>'
        cols.append(f'<section><h2>{label}</h2><ul>{items}</ul></section>')
    open_n = len(board["open"])
    open_html = ""
    if open_n:
        items = "".join(
            f'<li>{escape(c.get("date",""))} · {escape((c.get("code") or "?"))}'
            f' ({escape(c.get("shift_type",""))}) — {escape(c.get("name",""))}</li>'
            for c in board["open"][:8])
        open_html = f'<div class="open"><h2>⚠ Needs coverage ({open_n})</h2><ul>{items}</ul></div>'
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>On today — {escape(pretty)}</title>
<style>
  body {{ margin:0; font-family: system-ui, sans-serif; background:#0f141b; color:#e6eaf0; }}
  header {{ padding:24px 32px; border-bottom:1px solid #2a3441; }}
  header h1 {{ margin:0; font-size:2.2rem; }}
  header .d {{ color:#93a0b2; font-size:1.3rem; }}
  .board {{ display:flex; gap:24px; padding:24px 32px; flex-wrap:wrap; }}
  section {{ flex:1; min-width:240px; }}
  section h2 {{ font-size:1.4rem; color:#7aa2ff; border-bottom:2px solid #2a3441; padding-bottom:6px; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ font-size:1.5rem; padding:8px 0; border-bottom:1px solid #1b232e; }}
  li b {{ color:#fff; }}
  .none {{ color:#5b6675; }}
  .cov {{ color:#34d399; font-size:1rem; }}
  .open {{ margin:0 32px 32px; padding:16px 24px; background:#3a1d1d; border-radius:12px; }}
  .open h2 {{ color:#f87171; margin:0 0 8px; }}
  .open li {{ border-bottom:1px solid #4a2a2a; }}
</style></head><body>
<header><h1>On today</h1><div class="d">{escape(pretty)}</div></header>
<div class="board">{''.join(cols)}</div>
{open_html}
</body></html>"""


@app.get("/kiosk/{token}")
def kiosk(token: str):
    import datetime as _dt
    if token != store.kiosk_token():
        raise HTTPException(status_code=404, detail="unknown display")
    board = store.kiosk_board(_dt.date.today().isoformat())
    return Response(content=_kiosk_html(board), media_type="text/html; charset=utf-8")


# --------------------------------------------------------------------------
# public calendar feed (no auth — the token IS the secret)
# --------------------------------------------------------------------------
@app.get("/calendar/{token}.ics")
def calendar(token: str):
    person = store.person_by_token(token)
    if person is None:
        raise HTTPException(status_code=404, detail="unknown calendar")
    reminder = int(store.get_prefs(person["name"]).get("reminder_minutes") or 0)
    ics = build_ics(person["name"], person.get("shifts", []), config.TIMEZONE,
                    reminder_minutes=reminder)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{token}.ics"'},
    )


# --------------------------------------------------------------------------
# optional built-in scheduler (env AUTO_INGEST = daily | weekly | <seconds>)
# --------------------------------------------------------------------------
def _auto_interval() -> int | None:
    v = config.AUTO_INGEST
    if v in ("", "off", "0", "false", "no"):
        return None
    return {"daily": 86400, "weekly": 604800}.get(v, int(v) if v.isdigit() else None)


@app.on_event("startup")
async def _start_scheduler():
    interval = _auto_interval()
    if not interval:
        return
    import asyncio

    async def _loop():
        while True:
            await asyncio.sleep(interval)
            try:
                result = automation.ingest_latest(actor="scheduler")
                audit.log("scheduler", "auto_ingest", result)
            except Exception as exc:  # noqa: BLE001
                audit.log("scheduler", "auto_ingest_error", {"error": str(exc)})

    asyncio.create_task(_loop())


# --------------------------------------------------------------------------
# serve the built React SPA for everything else
# --------------------------------------------------------------------------
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "frontend not built yet — run `npm run build` in web/"},
        status_code=200,
    )
