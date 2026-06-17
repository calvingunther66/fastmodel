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

from . import config
from .accounts import AccountStore, has_cap, public_view
from .audit import AuditLog
from .coverage import propose as propose_coverage
from .ical import build_ics
from .store import ScheduleStore

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


def current_user(request: Request) -> dict | None:
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
    user = accounts.authenticate(creds.username, creds.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    request.session["user"] = user["username"]
    audit.log(user["username"], "login")
    return {"authenticated": True, "user": public_view(user)}


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
                            stats=store.aggregated_stats())


@app.get("/api/coverage/callouts")
def list_callouts(user: dict = Depends(require_auth)):
    return store.list_callouts()


@app.get("/api/coverage/stats")
def coverage_stats(user: dict = Depends(require_oversight)):
    return store.aggregated_stats()


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


@app.post("/api/coverage/clear")
def coverage_clear(payload: dict, user: dict = Depends(require_cap("manage_coverage"))):
    name, date, shift_type = _coverage_target(payload)
    store.clear_callout(name, date, shift_type)
    audit.log(user["username"], "clear_callout", {"name": name, "date": date, "shift": shift_type})
    return {"ok": True}


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
# public calendar feed (no auth — the token IS the secret)
# --------------------------------------------------------------------------
@app.get("/calendar/{token}.ics")
def calendar(token: str):
    person = store.person_by_token(token)
    if person is None:
        raise HTTPException(status_code=404, detail="unknown calendar")
    ics = build_ics(person["name"], person.get("shifts", []), config.TIMEZONE)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{token}.ics"'},
    )


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
