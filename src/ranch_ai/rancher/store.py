"""SQLite store shared by the nightly worker and the phone-app API.

Deliberately stdlib-only (sqlite3/json/hashlib) so the always-on API process
stays small on a 1 GB server. Tables:

* snapshots  - one JSON document per ranch run (latest is what the app shows)
* logs       - moves, rain gauge readings and notes sent from phones;
               client_id makes re-sends from a flaky connection idempotent
* sessions   - long-lived phone logins (only a hash of the token is stored)
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = Path(os.getenv("RANGEIQ_APP_DB", PROJECT_ROOT / "data" / "processed" / "rangeiq_app.sqlite"))
SESSION_DAYS = int(os.getenv("RANGEIQ_SESSION_DAYS", "60"))
LOG_KINDS = {"move", "rain", "note"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class AppStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_snap_ws ON snapshots(workspace_id, id);
                CREATE TABLE IF NOT EXISTS logs (
                    client_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT,
                    kind TEXT NOT NULL,
                    pasture_id TEXT,
                    payload TEXT NOT NULL,
                    logged_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_logs_ws ON logs(workspace_id, logged_at);
                CREATE TABLE IF NOT EXISTS terrain (
                    workspace_id TEXT PRIMARY KEY,
                    meta TEXT NOT NULL,
                    height BLOB NOT NULL,
                    texture BLOB NOT NULL,
                    texture_mime TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS photos (
                    client_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT,
                    user_name TEXT,
                    taken_at TEXT NOT NULL,
                    lat REAL, lon REAL, accuracy_m REAL, heading_deg REAL,
                    pasture_id TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    note TEXT,
                    analysis TEXT NOT NULL DEFAULT '{}',
                    flagged INTEGER NOT NULL DEFAULT 0,
                    bytes INTEGER,
                    received_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_photos_ws ON photos(workspace_id, taken_at);
                CREATE TABLE IF NOT EXISTS memberships (
                    user_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    name TEXT,
                    joined_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    max_uses INTEGER NOT NULL,
                    uses INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # -- snapshots -------------------------------------------------------------
    def save_snapshot(self, workspace_id: str, payload: dict[str, Any], keep: int = 120) -> None:
        generated_at = str(payload.get("generated_at") or _iso(utc_now()))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots(workspace_id, generated_at, payload) VALUES (?, ?, ?)",
                (workspace_id, generated_at, json.dumps(payload, separators=(",", ":"), default=str)),
            )
            conn.execute(
                "DELETE FROM snapshots WHERE workspace_id = ? AND id NOT IN "
                "(SELECT id FROM snapshots WHERE workspace_id = ? ORDER BY id DESC LIMIT ?)",
                (workspace_id, workspace_id, keep),
            )

    def latest_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM snapshots WHERE workspace_id = ? ORDER BY id DESC LIMIT 1", (workspace_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    # -- 3D terrain ---------------------------------------------------------------
    def save_terrain(self, workspace_id: str, meta: dict[str, Any], height: bytes, texture: bytes, texture_mime: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO terrain(workspace_id, meta, height, texture, texture_mime, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (workspace_id, json.dumps(meta), sqlite3.Binary(height), sqlite3.Binary(texture), texture_mime, _iso(utc_now())),
            )

    def terrain_meta(self, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT meta, updated_at FROM terrain WHERE workspace_id = ?", (workspace_id,)).fetchone()
        if row is None:
            return None
        return {**json.loads(row["meta"]), "updated_at": row["updated_at"]}

    def terrain_blob(self, workspace_id: str, part: str) -> tuple[bytes, str] | None:
        column = {"height": "height", "texture": "texture"}[part]
        with self._connect() as conn:
            row = conn.execute(f"SELECT {column} AS blob, texture_mime FROM terrain WHERE workspace_id = ?", (workspace_id,)).fetchone()
        if row is None:
            return None
        return bytes(row["blob"]), ("application/octet-stream" if part == "height" else row["texture_mime"])

    # -- logs ------------------------------------------------------------------
    def add_log(self, workspace_id: str, entry: dict[str, Any], user_id: str | None = None) -> tuple[dict[str, Any], bool]:
        """Insert a phone log entry. Returns (entry, created). Re-sends with the same client_id are no-ops."""
        client_id = str(entry.get("client_id") or "").strip()
        kind = str(entry.get("kind") or "").strip().lower()
        if not client_id or len(client_id) > 64:
            raise ValueError("client_id is required (max 64 characters).")
        if kind not in LOG_KINDS:
            raise ValueError(f"kind must be one of {sorted(LOG_KINDS)}.")
        logged_at = str(entry.get("logged_at") or _iso(utc_now()))
        payload = {k: v for k, v in entry.items() if k not in {"client_id", "kind", "logged_at", "pasture_id"}}
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM logs WHERE client_id = ?", (client_id,)).fetchone()
            if existing is not None:
                if existing["workspace_id"] != workspace_id:
                    raise ValueError("client_id already used.")
                return self._row_to_log(existing), False
            conn.execute(
                "INSERT INTO logs(client_id, workspace_id, user_id, kind, pasture_id, payload, logged_at, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (client_id, workspace_id, user_id, kind, entry.get("pasture_id"), json.dumps(payload), logged_at, _iso(utc_now())),
            )
            row = conn.execute("SELECT * FROM logs WHERE client_id = ?", (client_id,)).fetchone()
        return self._row_to_log(row), True

    def log_user(self, workspace_id: str, client_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT user_id FROM logs WHERE workspace_id = ? AND client_id = ?", (workspace_id, client_id)).fetchone()
        return row["user_id"] if row else None

    def delete_log(self, workspace_id: str, client_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE logs SET deleted = 1 WHERE workspace_id = ? AND client_id = ?", (workspace_id, client_id))
        return cur.rowcount > 0

    def list_logs(self, workspace_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM logs WHERE workspace_id = ? AND deleted = 0 ORDER BY logged_at DESC LIMIT ?",
                (workspace_id, int(limit)),
            ).fetchall()
        return [self._row_to_log(row) for row in rows]

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "client_id": row["client_id"],
            "kind": row["kind"],
            "pasture_id": row["pasture_id"],
            "logged_at": row["logged_at"],
            "received_at": row["received_at"],
            **json.loads(row["payload"] or "{}"),
        }

    # -- app secret (signs photo links) ------------------------------------------
    def secret(self) -> bytes:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = 'signing_secret'").fetchone()
            if row is None:
                value = secrets.token_hex(32)
                conn.execute("INSERT OR IGNORE INTO app_settings(key, value) VALUES ('signing_secret', ?)", (value,))
                row = conn.execute("SELECT value FROM app_settings WHERE key = 'signing_secret'").fetchone()
        return bytes.fromhex(row["value"])

    # -- photos ------------------------------------------------------------------
    def photo_dir(self, workspace_id: str) -> Path:
        base = Path(os.getenv("RANGEIQ_PHOTO_DIR", PROJECT_ROOT / "data" / "photos"))
        folder = base / "".join(ch for ch in workspace_id if ch.isalnum() or ch in "-_")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def add_photo(self, workspace_id: str, meta: dict[str, Any], image: bytes, thumb: bytes,
                  *, user_id: str | None, user_name: str | None) -> tuple[dict[str, Any], bool]:
        client_id = str(meta.get("client_id") or "").strip()
        if not client_id or len(client_id) > 64 or not all(ch.isalnum() or ch in "-_" for ch in client_id):
            raise ValueError("client_id is required (letters, numbers, - and _ only).")
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM photos WHERE client_id = ?", (client_id,)).fetchone()
            if existing is not None:
                if existing["workspace_id"] != workspace_id:
                    raise ValueError("client_id already used.")
                return self._row_to_photo(existing), False
        folder = self.photo_dir(workspace_id)
        (folder / f"{client_id}.jpg").write_bytes(image)
        (folder / f"{client_id}_t.jpg").write_bytes(thumb)

        def num(key: str) -> float | None:
            try:
                value = float(meta.get(key))
            except (TypeError, ValueError):
                return None
            return value if value == value else None

        tags = [str(t)[:40] for t in (meta.get("tags") or []) if str(t).strip()][:12]
        analysis = meta.get("analysis") if isinstance(meta.get("analysis"), dict) else {}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO photos(client_id, workspace_id, user_id, user_name, taken_at, lat, lon, accuracy_m, heading_deg, "
                "pasture_id, tags, note, analysis, flagged, bytes, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client_id, workspace_id, user_id, user_name, str(meta.get("taken_at") or _iso(utc_now())),
                 num("lat"), num("lon"), num("accuracy_m"), num("heading_deg"), meta.get("pasture_id"),
                 json.dumps(tags), (str(meta.get("note") or "")[:2000]) or None, json.dumps(analysis),
                 1 if meta.get("flagged") else 0, len(image), _iso(utc_now())),
            )
            row = conn.execute("SELECT * FROM photos WHERE client_id = ?", (client_id,)).fetchone()
        return self._row_to_photo(row), True

    def list_photos(self, workspace_id: str, limit: int = 300) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM photos WHERE workspace_id = ? AND deleted = 0 ORDER BY taken_at DESC LIMIT ?", (workspace_id, int(limit))
            ).fetchall()
        return [self._row_to_photo(r) for r in rows]

    def photo(self, workspace_id: str, client_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM photos WHERE workspace_id = ? AND client_id = ? AND deleted = 0",
                               (workspace_id, client_id)).fetchone()
        return self._row_to_photo(row) if row else None

    def photo_file(self, workspace_id: str, client_id: str, thumb: bool = False) -> Path | None:
        if self.photo(workspace_id, client_id) is None:
            return None
        path = self.photo_dir(workspace_id) / f"{client_id}{'_t' if thumb else ''}.jpg"
        return path if path.exists() else None

    def delete_photo(self, workspace_id: str, client_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE photos SET deleted = 1 WHERE workspace_id = ? AND client_id = ?", (workspace_id, client_id))
        return cur.rowcount > 0

    @staticmethod
    def _row_to_photo(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "client_id": row["client_id"], "user_id": row["user_id"], "by": row["user_name"], "taken_at": row["taken_at"],
            "lat": row["lat"], "lon": row["lon"], "accuracy_m": row["accuracy_m"], "heading_deg": row["heading_deg"],
            "pasture_id": row["pasture_id"], "tags": json.loads(row["tags"] or "[]"), "note": row["note"],
            "analysis": json.loads(row["analysis"] or "{}"), "flagged": bool(row["flagged"]), "received_at": row["received_at"],
        }

    # -- crew (ranch hands) ---------------------------------------------------------
    INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L

    def create_invite(self, workspace_id: str, created_by: str, days: int = 7, max_uses: int = 10) -> dict[str, Any]:
        raw = "".join(secrets.choice(self.INVITE_ALPHABET) for _ in range(6))
        code = f"{raw[:3]}-{raw[3:]}"
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO invites(code, workspace_id, created_by, created_at, expires_at, max_uses) VALUES (?, ?, ?, ?, ?, ?)",
                (code, workspace_id, created_by, _iso(now), _iso(now + timedelta(days=days)), max_uses),
            )
        return {"code": code, "expires_at": _iso(now + timedelta(days=days)), "max_uses": max_uses, "uses": 0}

    @staticmethod
    def normalize_code(code: str) -> str:
        cleaned = "".join(ch for ch in str(code).upper() if ch.isalnum())
        return f"{cleaned[:3]}-{cleaned[3:6]}" if len(cleaned) == 6 else cleaned

    def invite_valid(self, code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM invites WHERE code = ?", (self.normalize_code(code),)).fetchone()
        if row is None or row["revoked"] or row["uses"] >= row["max_uses"] or row["expires_at"] < _iso(utc_now()):
            return None
        return dict(row)

    def use_invite(self, code: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE invites SET uses = uses + 1 WHERE code = ?", (self.normalize_code(code),))

    def list_invites(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, expires_at, max_uses, uses FROM invites WHERE workspace_id = ? AND revoked = 0 AND expires_at >= ? "
                "AND uses < max_uses ORDER BY created_at DESC", (workspace_id, _iso(utc_now()))).fetchall()
        return [dict(r) for r in rows]

    def revoke_invite(self, workspace_id: str, code: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE invites SET revoked = 1 WHERE workspace_id = ? AND code = ?", (workspace_id, self.normalize_code(code)))
        return cur.rowcount > 0

    def add_member(self, user_id: str, workspace_id: str, name: str, role: str = "crew") -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO memberships(user_id, workspace_id, role, name, joined_at) VALUES (?, ?, ?, ?, ?)",
                         (user_id, workspace_id, role, name, _iso(utc_now())))

    def membership(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memberships WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def members(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id, name, role, joined_at FROM memberships WHERE workspace_id = ? ORDER BY joined_at",
                                (workspace_id,)).fetchall()
        return [dict(r) for r in rows]

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memberships WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cur.rowcount > 0

    def crew_user_ids(self) -> set[str]:
        with self._connect() as conn:
            return {r["user_id"] for r in conn.execute("SELECT user_id FROM memberships WHERE role = 'crew'").fetchall()}

    # -- sessions --------------------------------------------------------------
    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self, user_id: str, workspace_id: str, days: int = SESSION_DAYS) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash, user_id, workspace_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (self._hash(token), user_id, workspace_id, _iso(now), _iso(now + timedelta(days=days))),
            )
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(now),))
        return token

    def session(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (self._hash(token),)).fetchone()
        if row is None or row["expires_at"] < _iso(utc_now()):
            return None
        return {"user_id": row["user_id"], "workspace_id": row["workspace_id"]}

    def end_session(self, token: str | None) -> None:
        if token:
            with self._connect() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self._hash(token),))


def herd_days_by_pasture(logs: list[dict[str, Any]], today: datetime | None = None) -> dict[str, dict[str, int]]:
    """From move logs, days cattle have been IN each pasture, or days it has RESTED since they left."""
    today = today or utc_now()
    moves = sorted((log for log in logs if log.get("kind") == "move"), key=lambda log: log["logged_at"])
    last_in: dict[str, datetime] = {}
    last_out: dict[str, datetime] = {}
    for log in moves:
        when = datetime.fromisoformat(str(log["logged_at"]).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        to_id, from_id = log.get("pasture_id"), log.get("from_pasture_id")
        if from_id:
            last_out[from_id] = when
            last_in.pop(from_id, None)
        if to_id:
            last_in[to_id] = when
    result: dict[str, dict[str, int]] = {}
    for pid, when in last_in.items():
        result[pid] = {"days_in": max((today - when).days, 0)}
    for pid, when in last_out.items():
        if pid not in last_in:
            result[pid] = {"days_rested": max((today - when).days, 0)}
    return result
