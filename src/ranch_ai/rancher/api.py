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

import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Body, Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ranch_ai.rancher.store import PROJECT_ROOT, SESSION_DAYS, AppStore
from ranch_ai.services.auth_service import AuthError, AuthService

COOKIE = "rangeiq_session"
WEB_DIR = Path(os.getenv("RANGEIQ_WEB_DIR", PROJECT_ROOT / "web" / "app"))
AUTH_DB = Path(os.getenv("RANGEIQ_AUTH_DB", PROJECT_ROOT / "data" / "processed" / "rangeiq_auth.sqlite"))
SECURE_COOKIE = os.getenv("RANGEIQ_COOKIE_SECURE", "1") != "0"
# Where the phone app may be hosted besides this server (e.g. GitHub Pages). Comma-separated origins.
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("RANGEIQ_ALLOWED_ORIGINS", "https://zacharyslate.github.io").split(",") if o.strip()]
MAX_PHOTO_BYTES = 6 * 1024 * 1024
MAX_THUMB_BYTES = 400 * 1024
PHOTO_LINK_SECONDS = 6 * 3600
LOGIN_MAX_FAILURES = int(os.getenv("RANGEIQ_LOGIN_MAX_FAILURES", "8"))
LOGIN_WINDOW_SECONDS = int(os.getenv("RANGEIQ_LOGIN_WINDOW_SECONDS", "900"))


class LoginThrottle:
    """Refuse sign-in after too many recent failures for the same email or the same address."""

    def __init__(self, max_failures: int = LOGIN_MAX_FAILURES, window_seconds: int = LOGIN_WINDOW_SECONDS) -> None:
        self.max_failures, self.window = max_failures, window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._failures[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._recent(k, now)) >= self.max_failures for k in keys if k)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                if k:
                    self._recent(k, now).append(now)

    def clear(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


class _NoStoreStatic(StaticFiles):
    """Static files; the service worker script must never be cached by the browser."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path.endswith("sw.js") or path in {"", "index.html"}:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def create_app(
    store: AppStore | None = None,
    auth: AuthService | None = None,
    web_dir: Path | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="RangeIQ phone app API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store or AppStore()
    app.state.auth = auth or AuthService(AUTH_DB)
    app.state.throttle = LoginThrottle()
    # The app hosted elsewhere (GitHub Pages) signs in with a bearer token, not a cookie:
    # iPhone Safari blocks cross-site cookies, and tokens need no credentials mode.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins is not None else ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=86400,
    )

    def session(
        rangeiq_session: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        found = app.state.store.session(_bearer(authorization) or rangeiq_session)
        if found is None:
            raise HTTPException(status_code=401, detail="Please sign in.")
        member = app.state.store.membership(found["user_id"])
        if member is not None and member["workspace_id"] != found["workspace_id"]:
            raise HTTPException(status_code=401, detail="Please sign in.")
        return {**found, "role": member["role"] if member else "owner"}

    def owner_only(sess: dict[str, str] = Depends(session)) -> dict[str, str]:
        if sess["role"] != "owner":
            raise HTTPException(status_code=403, detail="Only the ranch owner can do that.")
        return sess

    def who(sess: dict[str, str]) -> str:
        user = app.state.auth.get_user_by_id(sess["user_id"])
        return (user.full_name if user else "") or "Someone"

    def client_key(request: Request) -> str:
        return "ip:" + (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else ""))

    def sign(workspace_id: str, client_id: str, kind: str, exp: int) -> str:
        msg = f"{workspace_id}|{client_id}|{kind}|{exp}".encode()
        return hmac.new(app.state.store.secret(), msg, hashlib.sha256).hexdigest()[:32]

    def photo_links(workspace_id: str, photo: dict[str, Any]) -> dict[str, Any]:
        # Round the expiry to the hour so the same photo keeps the same link for a while (phones can cache it).
        exp = (int(time.time()) + PHOTO_LINK_SECONDS) // 3600 * 3600 + 3600
        cid = photo["client_id"]
        base = f"/api/photo-file/{workspace_id}/{cid}"
        return {**photo,
                "image_url": f"{base}?kind=image&exp={exp}&sig={sign(workspace_id, cid, 'image', exp)}",
                "thumb_url": f"{base}?kind=thumb&exp={exp}&sig={sign(workspace_id, cid, 'thumb', exp)}"}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/login")
    def login(request: Request, response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        email = str(payload.get("email", "")).strip().lower()
        client = client_key(request)
        if app.state.throttle.blocked("email:" + email, client):
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait 15 minutes and try again.")
        try:
            user = app.state.auth.authenticate_user(email=email, password=str(payload.get("password", "")))
        except AuthError:
            app.state.throttle.fail("email:" + email, client)
            raise HTTPException(status_code=401, detail="That email and password don't match.") from None
        app.state.throttle.clear("email:" + email)
        member = app.state.store.membership(user.user_id)
        workspace = member["workspace_id"] if member else user.workspace_id
        token = app.state.store.create_session(user.user_id, workspace)
        response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/")
        return {"name": user.full_name, "ranch": user.ranch_name, "token": token, "role": member["role"] if member else "owner"}

    @app.post("/api/join")
    def join(request: Request, response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """A ranch hand signs up with the owner's crew code."""
        client = client_key(request)
        if app.state.throttle.blocked(client):
            raise HTTPException(status_code=429, detail="Too many attempts. Wait 15 minutes and try again.")
        invite = app.state.store.invite_valid(str(payload.get("code", "")))
        if invite is None:
            app.state.throttle.fail(client)
            raise HTTPException(status_code=400, detail="That crew code isn't valid or has expired. Ask the ranch owner for a new one.")
        owner_snapshot = app.state.store.latest_snapshot(invite["workspace_id"]) or {}
        ranch_name = (owner_snapshot.get("ranch") or {}).get("name") or "Crew"
        name = str(payload.get("name", "")).strip()[:80]
        try:
            user = app.state.auth.create_user(email=str(payload.get("email", "")), password=str(payload.get("password", "")),
                                              full_name=name, ranch_name=ranch_name, ranch_address="Crew member")
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        app.state.store.add_member(user.user_id, invite["workspace_id"], name, role="crew")
        app.state.store.use_invite(invite["code"])
        token = app.state.store.create_session(user.user_id, invite["workspace_id"])
        response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/")
        return {"name": user.full_name, "ranch": ranch_name, "token": token, "role": "crew"}

    @app.post("/api/logout")
    def logout(
        response: Response,
        rangeiq_session: str | None = Cookie(default=None),
        authorization: str | None = Header(default=None),
    ) -> dict[str, bool]:
        app.state.store.end_session(_bearer(authorization) or rangeiq_session)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        user = app.state.auth.get_user_by_id(sess["user_id"])
        if user is None:
            raise HTTPException(status_code=401, detail="Please sign in.")
        snap = app.state.store.latest_snapshot(sess["workspace_id"]) or {}
        ranch = (snap.get("ranch") or {}).get("name") or user.ranch_name
        return {"name": user.full_name, "email": user.email, "ranch": ranch, "role": sess["role"], "user_id": sess["user_id"]}

    # -- crew -------------------------------------------------------------------------
    @app.get("/api/crew")
    def crew(sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        return {"invites": app.state.store.list_invites(sess["workspace_id"]), "members": app.state.store.members(sess["workspace_id"])}

    @app.post("/api/crew/invites")
    def new_invite(sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        return app.state.store.create_invite(sess["workspace_id"], sess["user_id"])

    @app.delete("/api/crew/invites/{code}")
    def revoke_invite(code: str, sess: dict[str, str] = Depends(owner_only)) -> dict[str, bool]:
        return {"revoked": app.state.store.revoke_invite(sess["workspace_id"], code)}

    @app.delete("/api/crew/members/{user_id}")
    def remove_member(user_id: str, sess: dict[str, str] = Depends(owner_only)) -> dict[str, bool]:
        return {"removed": app.state.store.remove_member(sess["workspace_id"], user_id)}

    # -- photos -----------------------------------------------------------------------
    @app.post("/api/photos")
    async def upload_photo(meta: str = Form(...), photo: UploadFile = File(...), thumb: UploadFile = File(...),
                           sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        try:
            info = json.loads(meta)
            assert isinstance(info, dict)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Bad photo details.") from None
        image = await photo.read(MAX_PHOTO_BYTES + 1)
        small = await thumb.read(MAX_THUMB_BYTES + 1)
        if len(image) > MAX_PHOTO_BYTES or len(small) > MAX_THUMB_BYTES:
            raise HTTPException(status_code=413, detail="Photo is too large.")
        if image[:3] != b"\xff\xd8\xff" or small[:3] != b"\xff\xd8\xff":
            raise HTTPException(status_code=400, detail="Photos must be JPEG.")
        try:
            row, created = app.state.store.add_photo(sess["workspace_id"], info, image, small, user_id=sess["user_id"], user_name=who(sess))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"saved": row["client_id"], "created": created}

    @app.get("/api/photos")
    def list_photos(sess: dict[str, str] = Depends(session)) -> list[dict[str, Any]]:
        return [photo_links(sess["workspace_id"], p) for p in app.state.store.list_photos(sess["workspace_id"])]

    @app.delete("/api/photos/{client_id}")
    def delete_photo(client_id: str, sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        photo = app.state.store.photo(sess["workspace_id"], client_id)
        if photo is None:
            return {"deleted": False}
        if sess["role"] != "owner" and photo.get("user_id") != sess["user_id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own photos.")
        return {"deleted": app.state.store.delete_photo(sess["workspace_id"], client_id)}

    @app.get("/api/photo-file/{workspace_id}/{client_id}")
    def photo_file(workspace_id: str, client_id: str, kind: str = "image", exp: int = 0, sig: str = "") -> Response:
        # Signed, expiring links so <img> tags work without sign-in headers.
        if kind not in {"image", "thumb"} or exp < time.time() or not hmac.compare_digest(sig, sign(workspace_id, client_id, kind, exp)):
            raise HTTPException(status_code=403, detail="Link expired.")
        path = app.state.store.photo_file(workspace_id, client_id, thumb=(kind == "thumb"))
        if path is None:
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=21600"})

    @app.get("/api/snapshot")
    def snapshot(sess: dict[str, str] = Depends(session)) -> JSONResponse:
        data = app.state.store.latest_snapshot(sess["workspace_id"])
        if data is None:
            return JSONResponse({"pending": True, "message": "Your ranch is being set up. Check back after the next nightly update."})
        return JSONResponse(data, headers={"Cache-Control": "private, no-cache"})

    @app.get("/api/terrain/meta")
    def terrain_meta(sess: dict[str, str] = Depends(session)) -> JSONResponse:
        meta = app.state.store.terrain_meta(sess["workspace_id"])
        if meta is None:
            raise HTTPException(status_code=404, detail="3D terrain isn't ready yet. It's built with the next update.")
        return JSONResponse(meta, headers={"Cache-Control": "private, no-cache"})

    @app.get("/api/terrain/{part}")
    def terrain_part(part: str, sess: dict[str, str] = Depends(session)) -> Response:
        if part not in {"height", "texture"}:
            raise HTTPException(status_code=404)
        found = app.state.store.terrain_blob(sess["workspace_id"], part)
        if found is None:
            raise HTTPException(status_code=404, detail="3D terrain isn't ready yet.")
        blob, mime = found
        return Response(blob, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

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
                row, _created = app.state.store.add_log(sess["workspace_id"], {**entry, "by": who(sess)}, user_id=sess["user_id"])
                saved.append(row["client_id"])
            except ValueError as exc:
                errors.append({"client_id": entry.get("client_id"), "error": str(exc)})
        return {"saved": saved, "errors": errors}

    @app.delete("/api/logs/{client_id}")
    def delete_log(client_id: str, sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        if sess["role"] != "owner" and app.state.store.log_user(sess["workspace_id"], client_id) not in {None, sess["user_id"]}:
            raise HTTPException(status_code=403, detail="You can only delete your own entries.")
        return {"deleted": app.state.store.delete_log(sess["workspace_id"], client_id)}

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")

    folder = web_dir or WEB_DIR
    if folder.exists():
        app.mount("/app", _NoStoreStatic(directory=str(folder), html=True), name="app")
    return app


app = create_app()
