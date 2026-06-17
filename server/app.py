"""FastAPI app: shared-login schedule viewer + public per-person .ics feeds.

Routes
  POST /api/login                {username, password}  -> sets session cookie
  POST /api/logout
  GET  /api/me                                          -> {authenticated}
  GET  /api/schedule             (auth)                 -> parsed schedule JSON
  POST /api/schedule/upload      (auth)  multipart xlsx -> parse + store
  POST /api/schedule/reparse     (auth)  {sheet}        -> re-parse current xlsx
  GET  /api/people               (auth)                 -> [{name, ics_url}]
  GET  /calendar/{token}.ics     (PUBLIC)               -> text/calendar feed

The built React app (web/dist) is served for everything else.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .ical import build_ics
from .store import ScheduleStore

app = FastAPI(title="fastmodel schedule")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    same_site="lax",
    https_only=False,
)

store = ScheduleStore()
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class Credentials(BaseModel):
    username: str
    password: str


def require_auth(request: Request) -> None:
    if not request.session.get("auth"):
        raise HTTPException(status_code=401, detail="not authenticated")


@app.post("/api/login")
def login(creds: Credentials, request: Request):
    ok_user = secrets.compare_digest(creds.username, config.APP_USERNAME)
    ok_pass = secrets.compare_digest(creds.password, config.APP_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="invalid credentials")
    request.session["auth"] = True
    return {"authenticated": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/me")
def me(request: Request):
    return {"authenticated": bool(request.session.get("auth"))}


# --------------------------------------------------------------------------
# schedule
# --------------------------------------------------------------------------
@app.get("/api/schedule")
def get_schedule(request: Request, _: None = Depends(require_auth)):
    schedule = store.get_schedule()
    if schedule is None:
        return JSONResponse({"empty": True})
    return schedule


@app.post("/api/schedule/upload")
async def upload(
    request: Request,
    file: UploadFile,
    sheet: str | None = Form(default=None),
    _: None = Depends(require_auth),
):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="please upload an .xlsx file")
    data = await file.read()
    try:
        result = store.ingest(data, sheet_name=sheet)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not parse: {exc}")
    return {
        "parsed_sheet": result.get("parsed_sheet"),
        "available_sheets": result.get("available_sheets", []),
        "people": len([p for p in result.get("people", []) if p.get("name")]),
    }


@app.post("/api/schedule/reparse")
def reparse(payload: dict, request: Request, _: None = Depends(require_auth)):
    sheet = payload.get("sheet")
    if not sheet:
        raise HTTPException(status_code=400, detail="sheet is required")
    try:
        result = store.reparse(sheet)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="no workbook uploaded yet")
    return {"parsed_sheet": result.get("parsed_sheet")}


def _ics_base(request: Request) -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


@app.get("/api/people")
def people(request: Request, _: None = Depends(require_auth)):
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
