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

import base64
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
        # App files are small and change with each release: always check with the server (the service worker keeps
        # the offline copy). Without this, phones may reuse an old file by guesswork and mix old and new code.
        if not path.startswith("vendor/") and not path.endswith(".png"):
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
        role = role_on(found["user_id"], found["workspace_id"])
        if role is None:                     # removed from that ranch
            raise HTTPException(status_code=401, detail="Please sign in.")
        return {**found, "role": role}

    def role_on(user_id: str, workspace_id: str) -> str | None:
        """'owner' for your own ranch or as a partner, 'crew' for a ranch hand, None if no access."""
        member = app.state.store.membership(user_id, workspace_id)
        if member is not None:
            return member["role"]
        user = app.state.auth.get_user_by_id(user_id)
        return "owner" if user is not None and user.workspace_id == workspace_id else None

    def ranch_name(workspace_id: str, fallback: str = "Ranch") -> str:
        snap = app.state.store.latest_snapshot(workspace_id) or {}
        name = (snap.get("ranch") or {}).get("name")
        if not name:
            owners = app.state.auth.get_users_by_workspace(workspace_id)
            name = owners[0].ranch_name if owners else None
        return name or fallback

    def ranches_of(user) -> list[dict[str, Any]]:
        """Every ranch this person can open: their own (if it has a boundary or nothing else) and the ones they joined."""
        joined = [{"workspace_id": m["workspace_id"], "role": m["role"]} for m in app.state.store.memberships_of(user.user_id)]
        own_snap = app.state.store.latest_snapshot(user.workspace_id) or {}
        own_ready = bool(own_snap) and not own_snap.get("setup_needed")
        out = []
        if own_ready or not joined:
            out.append({"workspace_id": user.workspace_id, "role": "owner"})
        out += [j for j in joined if j["workspace_id"] != user.workspace_id]
        for r in out:
            r["name"] = ranch_name(r["workspace_id"], user.ranch_name if r["workspace_id"] == user.workspace_id else "Ranch")
        return out

    def signed_in_reply(user, workspace_id: str, response: Response) -> dict[str, Any]:
        token = app.state.store.create_session(user.user_id, workspace_id)
        response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/")
        return {"name": user.full_name, "ranch": ranch_name(workspace_id, user.ranch_name), "token": token,
                "role": role_on(user.user_id, workspace_id), "workspace_id": workspace_id, "ranches": ranches_of(user)}

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
        ranches = ranches_of(user)
        wanted = str(payload.get("ranch") or "")          # the phone remembers the last ranch used
        workspace = next((r["workspace_id"] for r in ranches if r["workspace_id"] == wanted), ranches[0]["workspace_id"])
        return signed_in_reply(user, workspace, response)

    @app.post("/api/join")
    def join(request: Request, response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Join a ranch with a code from its owner: a new ranch hand makes an account; someone who already has a
        RangeIQ login (e.g. the owner of another ranch) just adds this ranch with their email and password."""
        client = client_key(request)
        if app.state.throttle.blocked(client):
            raise HTTPException(status_code=429, detail="Too many attempts. Wait 15 minutes and try again.")
        invite = app.state.store.invite_valid(str(payload.get("code", "")))
        if invite is None:
            app.state.throttle.fail(client)
            raise HTTPException(status_code=400, detail="That crew code isn't valid or has expired. Ask the ranch owner for a new one.")
        name_of_ranch = ranch_name(invite["workspace_id"], "Crew")
        role = invite.get("role") or "crew"
        email, password = str(payload.get("email", "")), str(payload.get("password", ""))
        existing = app.state.auth.get_user_by_email(email) if email.strip() else None
        if existing is not None:
            try:
                user = app.state.auth.authenticate_user(email=email, password=password)
            except AuthError:
                app.state.throttle.fail(client)
                raise HTTPException(status_code=401, detail="You already have a RangeIQ login with that email. Use its password.") from None
            name = user.full_name
        else:
            name = str(payload.get("name", "")).strip()[:80]
            try:
                user = app.state.auth.create_user(email=email, password=password, full_name=name, ranch_name=name_of_ranch,
                                                  ranch_address="Crew member")
            except AuthError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
        if role_on(user.user_id, invite["workspace_id"]) != "owner":     # never downgrade an owner
            app.state.store.add_member(user.user_id, invite["workspace_id"], name, role=role)
        app.state.store.use_invite(invite["code"])
        return signed_in_reply(user, invite["workspace_id"], response)

    @app.get("/api/ranches")
    def ranches(sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        user = app.state.auth.get_user_by_id(sess["user_id"])
        return {"current": sess["workspace_id"], "ranches": ranches_of(user) if user else []}

    @app.post("/api/switch")
    def switch_ranch(response: Response, payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(session),
                     rangeiq_session: str | None = Cookie(default=None), authorization: str | None = Header(default=None)) -> dict[str, Any]:
        user = app.state.auth.get_user_by_id(sess["user_id"])
        target = str(payload.get("workspace_id") or "")
        if user is None or target not in {r["workspace_id"] for r in ranches_of(user)}:
            raise HTTPException(status_code=403, detail="You don't have access to that ranch.")
        app.state.store.end_session(_bearer(authorization) or rangeiq_session)
        return signed_in_reply(user, target, response)

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
        return {"name": user.full_name, "email": user.email, "ranch": ranch_name(sess["workspace_id"], user.ranch_name),
                "role": sess["role"], "user_id": sess["user_id"], "workspace_id": sess["workspace_id"], "ranches": ranches_of(user)}

    # -- crew -------------------------------------------------------------------------
    @app.get("/api/crew")
    def crew(sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        return {"invites": app.state.store.list_invites(sess["workspace_id"]), "members": app.state.store.members(sess["workspace_id"])}

    @app.post("/api/crew/invites")
    def new_invite(payload: dict[str, Any] | None = Body(default=None), sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        role = "owner" if (payload or {}).get("role") in {"owner", "partner"} else "crew"
        return app.state.store.create_invite(sess["workspace_id"], sess["user_id"], role=role)

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
        # The app asks for these by build date (?v=...), so a copy can be kept for a long time.
        return Response(blob, media_type=mime, headers={"Cache-Control": "private, max-age=2592000"})

    @app.post("/api/client-error")
    async def client_error(request: Request) -> dict[str, bool]:
        """Phones report a failed 3D load here so it shows up in the server log (no personal data is sent)."""
        body = (await request.body())[:1000].decode("utf-8", "replace").replace("\n", " ")
        print(f"[client-error] {body}", flush=True)
        return {"ok": True}

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

    @app.post("/api/resolve")
    def resolve(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        """Mark problem reports / photos resolved or reopen them: [{item_id, resolved, at, note}]. Anyone on the ranch."""
        items = payload if isinstance(payload, list) else [payload]
        if len(items) > 200 or not all(isinstance(i, dict) for i in items):
            raise HTTPException(status_code=400, detail="Send a list of at most 200 changes.")
        saved, errors = [], []
        for it in items:
            item_id = str(it.get("item_id") or "")[:64]
            try:
                app.state.store.resolve(sess["workspace_id"], item_id, bool(it.get("resolved")), user_id=sess["user_id"], user_name=who(sess),
                                        at=it.get("at"), note=it.get("note"))
                saved.append(item_id)
            except LookupError as exc:
                errors.append({"item_id": item_id, "error": str(exc), "retry": True})
            except ValueError as exc:
                errors.append({"item_id": item_id, "error": str(exc)})
        if saved:      # update pasture status soon instead of at the next hourly run
            ranch_setup.request_refresh(sess["workspace_id"])
        return {"saved": saved, "errors": errors}

    @app.delete("/api/logs/{client_id}")
    def delete_log(client_id: str, sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        if sess["role"] != "owner" and app.state.store.log_user(sess["workspace_id"], client_id) not in {None, sess["user_id"]}:
            raise HTTPException(status_code=403, detail="You can only delete your own entries.")
        return {"deleted": app.state.store.delete_log(sess["workspace_id"], client_id)}

    # -- ranch setup (owner): boundary, pasture names, ranch name, time zone ---------------
    from ranch_ai.rancher import setup as ranch_setup

    @app.get("/api/setup")
    def get_setup(sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        info = ranch_setup.describe(sess["workspace_id"])
        snap = app.state.store.latest_snapshot(sess["workspace_id"]) or {}
        info["pastures"] = [{"id": p["id"], "name": p["name"], "acres": p.get("acres")} for p in snap.get("pastures", [])]
        info["ranch"]["name"] = info["ranch"]["name"] or (snap.get("ranch") or {}).get("name")
        return info

    @app.post("/api/setup/boundary")
    async def setup_boundary(file: UploadFile = File(...), sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        data = await file.read(ranch_setup.MAX_BOUNDARY_BYTES + 1)
        try:
            return ranch_setup.save_boundary(sess["workspace_id"], file.filename or "boundary.kml", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/setup/ranch")
    def setup_ranch(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        try:
            return ranch_setup.set_ranch(sess["workspace_id"], name=payload.get("name"), timezone=payload.get("timezone"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/setup/names")
    def setup_names(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        return {"pasture_names": ranch_setup.set_pasture_names(sess["workspace_id"], {str(k): str(v) for k, v in payload.items()})}

    # -- drawn shapes: pasture boundaries (lockable) and roads / trails -----------------
    def boundaries_locked(workspace_id: str) -> bool:
        """Locked by default once the ranch has any pastures (drawn or from a file); open while there are none yet."""
        has_pastures = bool(app.state.store.list_shapes(workspace_id, "pasture")) or \
            bool((app.state.store.latest_snapshot(workspace_id) or {}).get("pastures"))
        return bool(app.state.store.ranch_setting(workspace_id, "boundaries_locked", has_pastures))

    def ensure_imported(workspace_id: str, sess: dict[str, str]) -> None:
        """Before the first boundary edit, copy the current pastures in, so drawing one never drops the others."""
        if not app.state.store.list_shapes(workspace_id, "pasture"):
            snap = app.state.store.latest_snapshot(workspace_id) or {}
            app.state.store.import_pastures(workspace_id, snap.get("pastures") or [], user_id=sess["user_id"], user_name=who(sess))

    @app.get("/api/shapes")
    def list_shapes(sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        shapes = app.state.store.list_shapes(sess["workspace_id"])
        return {"shapes": shapes, "boundaries_locked": boundaries_locked(sess["workspace_id"]),
                "boundary_source": "drawn" if any(s["kind"] == "pasture" for s in shapes) else "file"}

    @app.post("/api/shapes")
    def save_shapes(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        items = payload if isinstance(payload, list) else [payload]
        if len(items) > 200 or not all(isinstance(i, dict) for i in items):
            raise HTTPException(status_code=400, detail="Send a list of at most 200 shapes.")
        saved, errors, pastures_changed = [], [], False
        locked = boundaries_locked(sess["workspace_id"])
        if not locked and sess["role"] == "owner" and any(i.get("kind") == "pasture" for i in items):
            ensure_imported(sess["workspace_id"], sess)
        for item in items:
            try:
                row = app.state.store.save_shape(sess["workspace_id"], item, user_id=sess["user_id"], user_name=who(sess),
                                                 is_owner=sess["role"] == "owner", boundaries_locked=locked)
                saved.append(item.get("shape_id"))
                pastures_changed = pastures_changed or item.get("kind") == "pasture" or (row or {}).get("kind") == "pasture"
            except (ValueError, PermissionError) as exc:
                errors.append({"shape_id": item.get("shape_id"), "error": str(exc)})
        if pastures_changed:
            ranch_setup.request_refresh(sess["workspace_id"])
        return {"saved": saved, "errors": errors, "shapes": app.state.store.list_shapes(sess["workspace_id"]),
                "boundaries_locked": locked}

    @app.post("/api/boundaries/lock")
    def lock_boundaries(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(owner_only)) -> dict[str, Any]:
        locked = bool(payload.get("locked"))
        if not locked:
            ensure_imported(sess["workspace_id"], sess)   # first time editing: the uploaded pastures become editable
        app.state.store.set_ranch_setting(sess["workspace_id"], "boundaries_locked", locked)
        return {"boundaries_locked": locked, "shapes": app.state.store.list_shapes(sess["workspace_id"])}

    # -- places on the map (tanks, ponds, blinds, gates, ...) ----------------------------
    @app.get("/api/places")
    def list_places(sess: dict[str, str] = Depends(session)) -> list[dict[str, Any]]:
        return app.state.store.list_places(sess["workspace_id"])

    @app.post("/api/places")
    def save_places(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        items = payload if isinstance(payload, list) else [payload]
        if len(items) > 200 or not all(isinstance(i, dict) for i in items):
            raise HTTPException(status_code=400, detail="Send a list of at most 200 places.")
        saved, errors = [], []
        for item in items:
            try:
                if item.get("deleted"):
                    app.state.store.delete_place(sess["workspace_id"], str(item.get("place_id")), user_id=sess["user_id"],
                                                 is_owner=sess["role"] == "owner")
                else:
                    app.state.store.save_place(sess["workspace_id"], item, user_id=sess["user_id"], user_name=who(sess),
                                               is_owner=sess["role"] == "owner")
                saved.append(item.get("place_id"))
            except (ValueError, PermissionError) as exc:
                errors.append({"place_id": item.get("place_id"), "error": str(exc)})
        return {"saved": saved, "errors": errors, "places": app.state.store.list_places(sess["workspace_id"])}

    # -- to-do list: jobs anyone on the ranch can add and check off ----------------------
    def people(workspace_id: str) -> list[dict[str, str]]:
        owners = [{"user_id": u.user_id, "name": u.full_name or "Owner", "role": "owner"}
                  for u in app.state.auth.get_users_by_workspace(workspace_id)]
        crew = [{"user_id": m["user_id"], "name": m["name"] or "Crew", "role": m["role"]} for m in app.state.store.members(workspace_id)]
        seen, out = set(), []
        for p in owners + crew:
            if p["user_id"] not in seen:
                seen.add(p["user_id"]); out.append(p)
        return out

    # -- messenger --------------------------------------------------------------------
    # Text only. "all" = everyone on the ranch; or a direct conversation between two people. Anyone on the ranch can
    # write to anyone. Phones poll while the app is open; with notifications on, a push wakes the phone otherwise.
    from ranch_ai.rancher import push as webpush_mod

    def receipt_token(ws: str, uid: str, thread: str, at: str) -> str:
        """Lets the phone's service worker say "this notification arrived" without the sign-in token."""
        body = base64.urlsafe_b64encode(json.dumps([ws, uid, thread, at, int(time.time()) + 7 * 86400]).encode()).decode().rstrip("=")
        return body + "." + hmac.new(app.state.store.secret(), b"rcpt|" + body.encode(), hashlib.sha256).hexdigest()[:32]

    def delivered_now(ws: str, uid: str, msgs: list[dict[str, Any]]) -> None:
        newest: dict[str, str] = {}
        for m in msgs:
            if not m.get("deleted") and m.get("from_user") != uid and m["created_at"] > newest.get(m["thread_id"], ""):
                newest[m["thread_id"]] = m["created_at"]
        for thread, at in newest.items():
            app.state.store.mark_delivered(ws, uid, thread, at)

    @app.get("/api/messages")
    def list_messages(since: str | None = None, sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        ws, uid = sess["workspace_id"], sess["user_id"]
        msgs = app.state.store.list_messages(ws, uid, since=since)
        delivered_now(ws, uid, msgs)                 # these reached this phone: the senders' second tick
        # "now": where the phone should ask from next time (newest message or deletion it has seen)
        marks = [m.get("deleted_at") or m["created_at"] for m in msgs] + [m["created_at"] for m in msgs] + ([since] if since else [])
        everyone = people(ws)
        threads = ["all"] + [app.state.store.dm_thread(uid, p["user_id"]) for p in everyone if p["user_id"] != uid]
        return {"messages": msgs, "reads": app.state.store.reads(ws, uid), "people": everyone, "me": uid,
                "receipts": app.state.store.receipts(ws, threads), "now": max(marks) if marks else None}

    @app.post("/api/messages/delivered")
    def message_delivered(payload: dict[str, Any] = Body(...)) -> dict[str, bool]:
        """From the service worker when a notification arrives (signed receipt from the push itself, no sign-in)."""
        token = str(payload.get("receipt") or "")
        body, _, sig = token.partition(".")
        good = hmac.new(app.state.store.secret(), b"rcpt|" + body.encode(), hashlib.sha256).hexdigest()[:32]
        if not body or not hmac.compare_digest(sig, good):
            raise HTTPException(status_code=403, detail="Bad receipt.")
        ws, uid, thread, at, exp = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if exp < time.time():
            raise HTTPException(status_code=403, detail="Receipt expired.")
        app.state.store.mark_delivered(ws, uid, thread, at)
        return {"ok": True}

    @app.post("/api/messages")
    def send_messages(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        items = payload if isinstance(payload, list) else [payload]
        if len(items) > 100 or not all(isinstance(i, dict) for i in items):
            raise HTTPException(status_code=400, detail="Send at most 100 messages at a time.")
        ws, uid = sess["workspace_id"], sess["user_id"]
        everyone = people(ws)
        members = {p["user_id"] for p in everyone}
        saved, errors, fresh = [], [], []
        for it in items:
            try:
                row, created = app.state.store.add_message(ws, it, user_id=uid, user_name=who(sess), members=members)
                saved.append(row["msg_id"])
                if created:
                    fresh.append(row)
            except ValueError as exc:
                errors.append({"msg_id": it.get("msg_id"), "error": str(exc)})
        for row in fresh:                       # buzz everyone it's for, except the sender
            pair = app.state.store.thread_members(row["thread_id"])
            to = [p for p in (pair or members) if p != uid]
            ranch = ranch_name(ws)
            title = f"{row['from_name'] or 'Someone'}" + ("" if pair else f" → everyone{' · ' + ranch if ranch else ''}")
            for person in to:                      # one push each: each carries that person's signed delivery receipt
                webpush_mod.send_in_background(app.state.store, [person], {
                    "title": title, "body": row["text"][:180], "thread": row["thread_id"], "ws": ws, "tag": row["thread_id"],
                    "url": "/app/#chat", "receipt": receipt_token(ws, person, row["thread_id"], row["created_at"])})
        if fresh:
            app.state.store.mark_read(ws, uid, fresh[-1]["thread_id"], fresh[-1]["created_at"])
        return {"saved": saved, "errors": errors}

    @app.post("/api/messages/read")
    def read_messages(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        thread, at = str(payload.get("thread_id") or ""), str(payload.get("at") or "")[:40]
        if not thread or not at:
            raise HTTPException(status_code=400, detail="thread_id and at are required.")
        app.state.store.mark_read(sess["workspace_id"], sess["user_id"], thread, at)
        return {"ok": True}

    @app.delete("/api/messages/{msg_id}")
    def delete_message(msg_id: str, sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        try:
            return {"deleted": app.state.store.delete_message(sess["workspace_id"], msg_id, user_id=sess["user_id"],
                                                              is_owner=sess["role"] == "owner")}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

    @app.get("/api/push/key")
    def push_key(sess: dict[str, str] = Depends(session)) -> dict[str, str]:
        return {"key": webpush_mod.vapid_public_key(app.state.store)}

    @app.post("/api/push/subscribe")
    def push_subscribe(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        try:
            app.state.store.save_push_sub(sess["user_id"], payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"ok": True}

    @app.post("/api/push/unsubscribe")
    def push_unsubscribe(payload: dict[str, Any] = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, bool]:
        return {"ok": app.state.store.delete_push_sub(str(payload.get("endpoint") or ""), sess["user_id"])}

    @app.post("/api/push/test")
    def push_test(sess: dict[str, str] = Depends(session)) -> dict[str, int]:
        """Send a test notification to this person's phones (to check notifications work)."""
        return webpush_mod.send(app.state.store, [sess["user_id"]], {"title": "RangeIQ", "body": "Notifications are working.",
                                                                     "url": "/app/#messages", "tag": "test"})

    @app.get("/api/tasks")
    def list_tasks(sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        return {"tasks": app.state.store.list_tasks(sess["workspace_id"]), "people": people(sess["workspace_id"])}

    @app.post("/api/tasks")
    def task_ops(payload: Any = Body(...), sess: dict[str, str] = Depends(session)) -> dict[str, Any]:
        ops = payload if isinstance(payload, list) else [payload]
        if len(ops) > 200 or not all(isinstance(o, dict) for o in ops):
            raise HTTPException(status_code=400, detail="Send a list of at most 200 changes.")
        result = app.state.store.apply_task_ops(sess["workspace_id"], ops, user_id=sess["user_id"], user_name=who(sess),
                                                is_owner=sess["role"] == "owner")
        return {**result, "tasks": app.state.store.list_tasks(sess["workspace_id"])}

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")

    folder = web_dir or WEB_DIR
    if folder.exists():
        app.mount("/app", _NoStoreStatic(directory=str(folder), html=True), name="app")
    return app


app = create_app()
