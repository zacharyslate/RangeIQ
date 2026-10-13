"""Light API + static host for the RangeIQ phone app.

    uvicorn ranch_ai.rancher.api:app --host 127.0.0.1 --port 8502

Only reads what the nightly worker stored, plus phone logs. It never calls an
outside data source and never imports pandas, scikit-learn or rasterio, so it
answers fast and stays small on a 1 GB server.

Routes
    GET  /app/...            the installable phone app (static files)
    POST /api/login          email + password -> long-lived session cookie
    POST /api/logout
    GET  /api/me
    GET  /api/snapshot       latest ranch snapshot from the worker
    GET  /api/logs           recent moves / rain / notes
    POST /api/logs           add one or more entries (idempotent by client_id)
    DELETE /api/logs/{id}
    GET  /api/health
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Body, Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ranch_ai.rancher.store import PROJECT_ROOT, SESSION_DAYS, AppStore
from ranch_ai.services.auth_service import AuthError, AuthService

COOKIE = "rangeiq_session"
WEB_DIR = Path(os.getenv("RANGEIQ_WEB_DIR", PROJECT_ROOT / "web" / "app"))
AUTH_DB = Path(os.getenv("RANGEIQ_AUTH_DB", PROJECT_ROOT / "data" / "processed" / "rangeiq_auth.sqlite"))
SECURE_COOKIE = os.getenv("RANGEIQ_COOKIE_SECURE", "1") != "0"


class _NoStoreStatic(StaticFiles):
    """Static files; the service worker script must never be cached by the browser."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path.endswith("sw.js") or path in {"", "index.html"}:
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(store: AppStore | None = None, auth: AuthService | None = None, web_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="RangeIQ phone app API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store or AppStore()
    app.state.auth = auth or AuthService(AUTH_DB)

    def session(rangeiq_session: str | None = Cookie(default=None)) -> dict[str, str]:
        found = app.state.store.session(rangeiq_session)
        if found is None:
            raise HTTPException(status_code=401, detail="Please sign in.")
        return found

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/login")
    def login(response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            user = app.state.auth.authenticate_user(email=str(payload.get("email", "")), password=str(payload.get("password", "")))
        except AuthError:
            raise HTTPException(status_code=401, detail="That email and password don't match.") from None
        token = app.state.store.create_session(user.user_id, user.workspace_id)
        response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/")
        return {"name": user.full_name, "ranch": user.ranch_name}

    @app.post("/api/logout")
    def logout(response: Response, rangeiq_session: str | None = Cookie(default=None)) -> dict[str, bool]:
        app.state.store.end_session(rangeiq_session)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        user = app.state.auth.get_user_by_id(sess["user_id"])
        if user is None:
            raise HTTPException(status_code=401, detail="Please sign in.")
        return {"name": user.full_name, "email": user.email, "ranch": user.ranch_name}

    @app.get("/api/snapshot")
    def snapshot(sess: dict[str, str] = Depends(session)) -> JSONResponse:
        data = app.state.store.latest_snapshot(sess["workspace_id"])
        if data is None:
            return JSONResponse({"pending": True, "message": "Your ranch is being set up. Check back after the next nightly update."})
        return JSONResponse(data, headers={"Cache-Control": "private, no-cache"})

    @app.get("/api/logs")
    def list_logs(sess: dict[str, str] = Depends(session)) -> list[dict[str, Any]]:
        return app.state.store.list_logs(sess["workspace_id"])

    @app.post("/api/logs")
    def add_logs(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        entries = payload if isinstance(payload, list) else [payload]
        if len(entries) > 200:
            raise HTTPException(status_code=413, detail="Send at most 200 entries at a time.")
        saved, errors = [], []
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append({"client_id": None, "error": "Each entry must be an object."})
                continue
            try:
                row, _created = app.state.store.add_log(sess["workspace_id"], entry, user_id=sess["user_id"])
                saved.append(row["client_id"])
            except ValueError as exc:
                errors.append({"client_id": entry.get("client_id"), "error": str(exc)})
        return {"saved": saved, "errors": errors}

    @app.delete("/api/logs/{client_id}")
    def delete_log(client_id: str, sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        return {"deleted": app.state.store.delete_log(sess["workspace_id"], client_id)}

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")

    folder = web_dir or WEB_DIR
    if folder.exists():
        app.mount("/app", _NoStoreStatic(directory=str(folder), html=True), name="app")
    return app


app = create_app()
