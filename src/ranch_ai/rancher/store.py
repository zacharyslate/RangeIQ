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
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = Path(os.getenv("RANGEIQ_APP_DB", PROJECT_ROOT / "data" / "processed" / "rangeiq_app.sqlite"))
# Phone sign-ins last a year and renew themselves whenever the app is used, so nobody has to keep signing in.
SESSION_DAYS = int(os.getenv("RANGEIQ_SESSION_DAYS", "365"))
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
                -- One person can be on several ranches (e.g. owner of one, partner or crew on another).
                CREATE TABLE IF NOT EXISTS ranch_members (
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    name TEXT,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, workspace_id)
                );
                INSERT OR IGNORE INTO ranch_members(user_id, workspace_id, role, name, joined_at)
                    SELECT user_id, workspace_id, role, name, joined_at FROM memberships;
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
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    note TEXT,
                    pasture_id TEXT,
                    due_date TEXT,
                    repeat_days INTEGER NOT NULL DEFAULT 0,
                    assignee_id TEXT,
                    lat REAL, lon REAL,
                    source_id TEXT,
                    created_by TEXT, created_by_name TEXT, created_at TEXT NOT NULL,
                    done_at TEXT, done_by TEXT, done_by_name TEXT,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_tasks_ws ON tasks(workspace_id);
                -- Fixed places on the ranch map: water tanks, ponds, blinds, feeders, gates, pens, ...
                CREATE TABLE IF NOT EXISTS places (
                    place_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    note TEXT,
                    lat REAL NOT NULL, lon REAL NOT NULL,
                    photo_id TEXT,
                    created_by TEXT, created_by_name TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_places_ws ON places(workspace_id);
                -- Shapes drawn in the app: pasture boundaries (closed) and roads / trails / lines (open).
                CREATE TABLE IF NOT EXISTS shapes (
                    shape_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,              -- 'pasture' or a line type
                    name TEXT NOT NULL,
                    note TEXT,
                    coords TEXT NOT NULL,            -- JSON [[lon, lat], ...]
                    source TEXT,                     -- 'drawn', 'gps', 'imported'
                    created_by TEXT, created_by_name TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (workspace_id, shape_id)
                );
                CREATE TABLE IF NOT EXISTS ranch_settings (
                    workspace_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, key)
                );
                CREATE TABLE IF NOT EXISTS task_ops (
                    op_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    op TEXT NOT NULL,
                    user_id TEXT, user_name TEXT,
                    at TEXT NOT NULL,
                    prev TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_task_ops ON task_ops(workspace_id, task_id, at);
                -- A problem report or photo marked resolved (or reopened). Last change wins. via_task: resolved by checking off
                -- the job that was made from it, so undoing that check-off reopens it.
                CREATE TABLE IF NOT EXISTS resolutions (
                    workspace_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    resolved INTEGER NOT NULL,
                    at TEXT NOT NULL,
                    user_id TEXT,
                    user_name TEXT,
                    note TEXT,
                    via_task TEXT,
                    PRIMARY KEY (workspace_id, item_id)
                );
                -- Messenger: "all" is the whole ranch; "dm:<a>|<b>" is two people (user ids sorted). created_at is the server's
                -- clock and orders the conversation; sent_at is when the phone sent it (it may have been offline).
                CREATE TABLE IF NOT EXISTS messages (
                    msg_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    from_user TEXT NOT NULL,
                    from_name TEXT,
                    text TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_messages ON messages(workspace_id, created_at);
                CREATE TABLE IF NOT EXISTS message_reads (
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, user_id, thread_id)
                );
                -- "Delivered" ticks: the newest message in a thread that reached this person's phone (the app fetched it,
                -- or a notification for it arrived).
                CREATE TABLE IF NOT EXISTS message_delivered (
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, user_id, thread_id)
                );
                -- Profile pictures (one per person, used on every ranch they're on). The file is <photo dir>/avatars/<user>.jpg.
                CREATE TABLE IF NOT EXISTS avatars (
                    user_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL
                );
                -- Phones that asked for notifications (Web Push). One row per phone/browser.
                CREATE TABLE IF NOT EXISTS push_subs (
                    endpoint TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TEXT NOT NULL
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
            if "device_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(places)").fetchall()}:
                conn.execute("ALTER TABLE places ADD COLUMN device_id TEXT")
            photo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(photos)").fetchall()}
            if "place_id" not in photo_cols:
                conn.execute("ALTER TABLE photos ADD COLUMN place_id TEXT")
            if "shape_id" not in photo_cols:
                conn.execute("ALTER TABLE photos ADD COLUMN shape_id TEXT")
            # A photo can belong to a report / rain / cattle-move entry (log_id) or to a job (task_id).
            for col in ("log_id", "task_id"):
                if col not in photo_cols:
                    conn.execute(f"ALTER TABLE photos ADD COLUMN {col} TEXT")
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(invites)").fetchall()}
            if "role" not in cols:
                conn.execute("ALTER TABLE invites ADD COLUMN role TEXT NOT NULL DEFAULT 'crew'")

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
        payload = {k: v for k, v in entry.items() if k not in {"client_id", "kind", "logged_at", "pasture_id", "user_id"}}
        # Location of a report (for the map): keep only sensible numbers.
        for key, low, high in (("lat", -90, 90), ("lon", -180, 180), ("accuracy_m", 0, 100000)):
            if key in payload:
                try:
                    value = float(payload[key])
                    payload[key] = value if low <= value <= high else None
                except (TypeError, ValueError):
                    payload[key] = None
                if payload[key] is None:
                    payload.pop(key)
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
        res = self.resolutions(workspace_id)
        return [{**self._row_to_log(row), **res.get(row["client_id"], {})} for row in rows]

    # -- resolving problems ------------------------------------------------------------
    def resolutions(self, workspace_id: str) -> dict[str, dict[str, Any]]:
        """{item_id: {resolved_at, resolved_by, resolve_note, resolved_via}} for items currently resolved."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM resolutions WHERE workspace_id = ? AND resolved = 1", (workspace_id,)).fetchall()
        return {r["item_id"]: {"resolved_at": r["at"], "resolved_by": r["user_name"], "resolve_note": r["note"], "resolved_via": r["via_task"]}
                for r in rows}

    @staticmethod
    def _set_resolution(conn: sqlite3.Connection, workspace_id: str, item_id: str, resolved: bool, at: str, user_id: str | None,
                        user_name: str | None, note: str | None = None, via_task: str | None = None) -> bool:
        old = conn.execute("SELECT at FROM resolutions WHERE workspace_id = ? AND item_id = ?", (workspace_id, item_id)).fetchone()
        if old is not None and str(old["at"]) > at:          # a newer change already arrived (phones sync late)
            return False
        conn.execute("INSERT OR REPLACE INTO resolutions(workspace_id, item_id, resolved, at, user_id, user_name, note, via_task) "
                     "VALUES (?,?,?,?,?,?,?,?)", (workspace_id, item_id, 1 if resolved else 0, at, user_id, user_name,
                                                  (note or "").strip()[:1000] or None, via_task))
        return True

    def resolve(self, workspace_id: str, item_id: str, resolved: bool, *, user_id: str, user_name: str, at: str | None = None,
                note: str | None = None) -> bool:
        """Mark a report (log entry) or a photo resolved, or reopen it. Anyone on the ranch may do this."""
        at = str(at or _iso(utc_now()))
        datetime.fromisoformat(at.replace("Z", "+00:00"))       # ValueError on junk
        with self._connect() as conn:
            found = conn.execute("SELECT 1 FROM logs WHERE workspace_id = ? AND client_id = ? AND deleted = 0 UNION "
                                 "SELECT 1 FROM photos WHERE workspace_id = ? AND client_id = ? AND deleted = 0",
                                 (workspace_id, item_id, workspace_id, item_id)).fetchone()
            if found is None:
                raise LookupError("No such report or photo (it may not have reached the server yet).")
            return self._set_resolution(conn, workspace_id, item_id, resolved, at, user_id, user_name, note)

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "client_id": row["client_id"],
            "kind": row["kind"],
            "pasture_id": row["pasture_id"],
            "logged_at": row["logged_at"],
            "received_at": row["received_at"],
            **json.loads(row["payload"] or "{}"),
            "user_id": row["user_id"],
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

    # -- messenger -----------------------------------------------------------------
    MESSAGE_MAX = 2000

    @staticmethod
    def dm_thread(a: str, b: str) -> str:
        return "dm:" + "|".join(sorted([a, b]))

    @staticmethod
    def thread_members(thread_id: str) -> list[str] | None:
        """The two people in a direct thread, or None for the whole-ranch thread."""
        return thread_id[3:].split("|") if thread_id.startswith("dm:") else None

    def add_message(self, workspace_id: str, data: dict[str, Any], *, user_id: str, user_name: str,
                    members: set[str]) -> tuple[dict[str, Any], bool]:
        """Save one message (re-sends with the same msg_id are no-ops). `members` = everyone on this ranch."""
        msg_id = str(data.get("msg_id") or "").strip()
        if not msg_id or len(msg_id) > 64:
            raise ValueError("msg_id is required.")
        text = str(data.get("text") or "").strip()
        if not text:
            raise ValueError("A message can't be empty.")
        if len(text) > self.MESSAGE_MAX:
            raise ValueError(f"Keep messages under {self.MESSAGE_MAX} characters.")
        to = data.get("to_user_id")
        thread = str(data.get("thread_id") or "")
        if to:
            if to == user_id or to not in members:
                raise ValueError("That person isn't on this ranch.")
            thread = self.dm_thread(user_id, str(to))
        elif thread != "all":
            pair = self.thread_members(thread)
            if not pair or len(pair) != 2 or user_id not in pair or any(p not in members for p in pair) or pair[0] == pair[1]:
                raise ValueError("Unknown conversation.")
            thread = self.dm_thread(*pair)
        sent_at = str(data.get("sent_at") or _iso(utc_now()))[:40]
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,)).fetchone()
            if row is not None:
                if row["workspace_id"] != workspace_id or row["from_user"] != user_id:
                    raise ValueError("msg_id already used.")
                return self._row_to_message(row), False
            created = utc_now().isoformat(timespec="microseconds")
            conn.execute("INSERT INTO messages(msg_id, workspace_id, thread_id, from_user, from_name, text, sent_at, created_at) "
                         "VALUES (?,?,?,?,?,?,?,?)", (msg_id, workspace_id, thread, user_id, user_name, text, sent_at, created))
            row = conn.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,)).fetchone()
        return self._row_to_message(row), True

    def list_messages(self, workspace_id: str, user_id: str, since: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        """Messages this person can see (the whole-ranch thread + their direct threads). With `since` (a created_at from
        an earlier answer), only newer ones, plus any deleted since then (so phones drop them too)."""
        mine = "(thread_id = 'all' OR thread_id LIKE ? OR thread_id LIKE ?)"
        args: list[Any] = [workspace_id, f"dm:{user_id}|%", f"dm:%|{user_id}"]
        with self._connect() as conn:
            if since:
                rows = conn.execute(f"SELECT * FROM messages WHERE workspace_id = ? AND {mine} AND (created_at > ? OR deleted_at > ?) "
                                    "ORDER BY created_at LIMIT ?", (*args, since, since, int(limit))).fetchall()
            else:
                rows = conn.execute(f"SELECT * FROM (SELECT * FROM messages WHERE workspace_id = ? AND {mine} AND deleted_at IS NULL "
                                    "ORDER BY created_at DESC LIMIT ?) ORDER BY created_at", (*args, int(limit))).fetchall()
        return [self._row_to_message(r) for r in rows]

    def delete_message(self, workspace_id: str, msg_id: str, *, user_id: str, is_owner: bool) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE workspace_id = ? AND msg_id = ?", (workspace_id, msg_id)).fetchone()
            if row is None or row["deleted_at"]:
                return False
            if row["from_user"] != user_id and not is_owner:
                raise PermissionError("You can only delete your own messages.")
            conn.execute("UPDATE messages SET deleted_at = ? WHERE msg_id = ?", (utc_now().isoformat(timespec="microseconds"), msg_id))
        return True

    def mark_read(self, workspace_id: str, user_id: str, thread_id: str, read_at: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO message_reads(workspace_id, user_id, thread_id, read_at) VALUES (?,?,?,?) "
                         "ON CONFLICT(workspace_id, user_id, thread_id) DO UPDATE SET read_at = MAX(read_at, excluded.read_at)",
                         (workspace_id, user_id, thread_id, read_at))

    def mark_delivered(self, workspace_id: str, user_id: str, thread_id: str, at: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO message_delivered(workspace_id, user_id, thread_id, at) VALUES (?,?,?,?) "
                         "ON CONFLICT(workspace_id, user_id, thread_id) DO UPDATE SET at = MAX(at, excluded.at)",
                         (workspace_id, user_id, thread_id, at))

    def receipts(self, workspace_id: str, thread_ids: Iterable[str]) -> dict[str, dict[str, dict[str, str]]]:
        """{thread: {user_id: {"delivered": at, "read": at}}}: how far each person has received and read each thread.
        Reading implies delivered."""
        ids = list(set(thread_ids))
        out: dict[str, dict[str, dict[str, str]]] = {t: {} for t in ids}
        if not ids:
            return out
        q = ",".join("?" * len(ids))
        with self._connect() as conn:
            for table, key in (("message_delivered", "delivered"), ("message_reads", "read")):
                col = "at" if table == "message_delivered" else "read_at"
                for r in conn.execute(f"SELECT user_id, thread_id, {col} AS at FROM {table} WHERE workspace_id = ? AND thread_id IN ({q})",
                                      (workspace_id, *ids)).fetchall():
                    out[r["thread_id"]].setdefault(r["user_id"], {})[key] = r["at"]
        for per in out.values():
            for v in per.values():
                if v.get("read") and v["read"] > v.get("delivered", ""):
                    v["delivered"] = v["read"]
        return out

    def reads(self, workspace_id: str, user_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT thread_id, read_at FROM message_reads WHERE workspace_id = ? AND user_id = ?",
                                (workspace_id, user_id)).fetchall()
        return {r["thread_id"]: r["read_at"] for r in rows}

    def unread_count(self, workspace_id: str, user_id: str) -> int:
        reads = self.reads(workspace_id, user_id)
        return sum(1 for m in self.list_messages(workspace_id, user_id)
                   if m["from_user"] != user_id and m["created_at"] > reads.get(m["thread_id"], ""))

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
        out = {k: row[k] for k in ("msg_id", "thread_id", "from_user", "from_name", "text", "sent_at", "created_at")}
        if row["deleted_at"]:
            out = {"msg_id": row["msg_id"], "thread_id": row["thread_id"], "deleted": True, "created_at": row["created_at"],
                   "deleted_at": row["deleted_at"]}
        return out

    # -- profile pictures ---------------------------------------------------------------
    def avatar_path(self, user_id: str) -> Path:
        base = Path(os.getenv("RANGEIQ_PHOTO_DIR", PROJECT_ROOT / "data" / "photos")) / "avatars"
        base.mkdir(parents=True, exist_ok=True)
        return base / ("".join(ch for ch in user_id if ch.isalnum() or ch in "-_") + ".jpg")

    def set_avatar(self, user_id: str, jpeg: bytes) -> str:
        self.avatar_path(user_id).write_bytes(jpeg)
        stamp = utc_now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO avatars(user_id, updated_at) VALUES (?, ?)", (user_id, stamp))
        return stamp

    def remove_avatar(self, user_id: str) -> bool:
        self.avatar_path(user_id).unlink(missing_ok=True)
        with self._connect() as conn:
            return conn.execute("DELETE FROM avatars WHERE user_id = ?", (user_id,)).rowcount > 0

    def avatar_versions(self, user_ids: Iterable[str]) -> dict[str, str]:
        ids = list(set(user_ids))
        if not ids:
            return {}
        with self._connect() as conn:
            rows = conn.execute(f"SELECT user_id, updated_at FROM avatars WHERE user_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        return {r["user_id"]: r["updated_at"] for r in rows}

    # -- push notifications (Web Push) ------------------------------------------------
    def save_push_sub(self, user_id: str, sub: dict[str, Any]) -> None:
        endpoint = str(sub.get("endpoint") or "")
        keys = sub.get("keys") or {}
        if not endpoint.startswith("https://") or len(endpoint) > 1000 or not keys.get("p256dh") or not keys.get("auth"):
            raise ValueError("Bad subscription.")
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO push_subs(endpoint, user_id, p256dh, auth, created_at) VALUES (?,?,?,?,?)",
                         (endpoint, user_id, str(keys["p256dh"])[:200], str(keys["auth"])[:100], _iso(utc_now())))

    def delete_push_sub(self, endpoint: str, user_id: str | None = None) -> bool:
        with self._connect() as conn:
            if user_id:
                cur = conn.execute("DELETE FROM push_subs WHERE endpoint = ? AND user_id = ?", (endpoint, user_id))
            else:
                cur = conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        return cur.rowcount > 0

    def push_subs_for(self, user_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = list(set(user_ids))
        if not ids:
            return []
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM push_subs WHERE user_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        return [dict(r) for r in rows]

    def app_value(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_app_value_once(self, key: str, value: str) -> str:
        """Store a value unless one is there already; returns the stored one (first writer wins)."""
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO app_settings(key, value) VALUES (?, ?)", (key, value))
            return conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()["value"]

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
                "pasture_id, tags, note, analysis, flagged, bytes, received_at, place_id, shape_id, log_id, task_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client_id, workspace_id, user_id, user_name, str(meta.get("taken_at") or _iso(utc_now())),
                 num("lat"), num("lon"), num("accuracy_m"), num("heading_deg"), meta.get("pasture_id"),
                 json.dumps(tags), (str(meta.get("note") or "")[:2000]) or None, json.dumps(analysis),
                 1 if meta.get("flagged") else 0, len(image), _iso(utc_now()),
                 (str(meta.get("place_id"))[:64] if meta.get("place_id") else None),
                 (str(meta.get("shape_id"))[:64] if meta.get("shape_id") else None),
                 (str(meta.get("log_id"))[:64] if meta.get("log_id") else None),
                 (str(meta.get("task_id"))[:64] if meta.get("task_id") else None)),
            )
            row = conn.execute("SELECT * FROM photos WHERE client_id = ?", (client_id,)).fetchone()
        return self._row_to_photo(row), True

    def list_photos(self, workspace_id: str, limit: int = 300) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM photos WHERE workspace_id = ? AND deleted = 0 ORDER BY taken_at DESC LIMIT ?", (workspace_id, int(limit))
            ).fetchall()
        res = self.resolutions(workspace_id)
        return [{**self._row_to_photo(r), **res.get(r["client_id"], {})} for r in rows]

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
            "pasture_id": row["pasture_id"], "tags": json.loads(row["tags"] or "[]"), "note": row["note"], "place_id": row["place_id"], "shape_id": row["shape_id"],
            "log_id": row["log_id"], "task_id": row["task_id"],
            "analysis": json.loads(row["analysis"] or "{}"), "flagged": bool(row["flagged"]), "received_at": row["received_at"],
        }

    # -- crew (ranch hands) ---------------------------------------------------------
    INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L

    def create_invite(self, workspace_id: str, created_by: str, days: int = 7, max_uses: int = 10, role: str = "crew") -> dict[str, Any]:
        """role 'crew' = ranch hand; 'owner' = partner with the same rights as the owner (crew, settings)."""
        if role not in {"crew", "owner"}:
            raise ValueError("role must be crew or owner")
        if role == "owner":
            days, max_uses = 2, 1
        raw = "".join(secrets.choice(self.INVITE_ALPHABET) for _ in range(6))
        code = f"{raw[:3]}-{raw[3:]}"
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO invites(code, workspace_id, created_by, created_at, expires_at, max_uses, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, workspace_id, created_by, _iso(now), _iso(now + timedelta(days=days)), max_uses, role),
            )
        return {"code": code, "expires_at": _iso(now + timedelta(days=days)), "max_uses": max_uses, "uses": 0, "role": role}

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
                "SELECT code, expires_at, max_uses, uses, role FROM invites WHERE workspace_id = ? AND revoked = 0 AND expires_at >= ? "
                "AND uses < max_uses ORDER BY created_at DESC", (workspace_id, _iso(utc_now()))).fetchall()
        return [dict(r) for r in rows]

    def revoke_invite(self, workspace_id: str, code: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE invites SET revoked = 1 WHERE workspace_id = ? AND code = ?", (workspace_id, self.normalize_code(code)))
        return cur.rowcount > 0

    def add_member(self, user_id: str, workspace_id: str, name: str, role: str = "crew") -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO ranch_members(user_id, workspace_id, role, name, joined_at) VALUES (?, ?, ?, ?, ?)",
                         (user_id, workspace_id, role, name, _iso(utc_now())))

    def membership(self, user_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        """This person's membership of one ranch (or their most recent one)."""
        with self._connect() as conn:
            if workspace_id is None:
                row = conn.execute("SELECT * FROM ranch_members WHERE user_id = ? ORDER BY joined_at DESC LIMIT 1", (user_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM ranch_members WHERE user_id = ? AND workspace_id = ?", (user_id, workspace_id)).fetchone()
        return dict(row) if row else None

    def memberships_of(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM ranch_members WHERE user_id = ? ORDER BY joined_at", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def members(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id, name, role, joined_at FROM ranch_members WHERE workspace_id = ? ORDER BY joined_at",
                                (workspace_id,)).fetchall()
        return [dict(r) for r in rows]

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM ranch_members WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
            conn.execute("DELETE FROM memberships WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
            conn.execute("DELETE FROM sessions WHERE user_id = ? AND workspace_id = ?", (user_id, workspace_id))
        return cur.rowcount > 0

    def crew_user_ids(self) -> set[str]:
        with self._connect() as conn:
            return {r["user_id"] for r in conn.execute("SELECT user_id FROM ranch_members WHERE role = 'crew'").fetchall()}

    # -- per-ranch settings ---------------------------------------------------------
    def ranch_setting(self, workspace_id: str, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM ranch_settings WHERE workspace_id = ? AND key = ?", (workspace_id, key)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_ranch_setting(self, workspace_id: str, key: str, value: Any) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO ranch_settings(workspace_id, key, value) VALUES (?, ?, ?)", (workspace_id, key, json.dumps(value)))

    # -- drawn shapes: pasture boundaries, roads, trails -----------------------------
    LINE_KINDS = {"main_road", "ranch_road", "two_track", "game_trail", "hunting_trail", "path", "fence", "water_line", "creek", "other_line"}

    def list_shapes(self, workspace_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM shapes WHERE workspace_id = ? AND deleted = 0", [workspace_id]
        if kind:
            sql += " AND kind = ?"; args.append(kind)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY name", args).fetchall()
        return [{**{k: r[k] for k in ("shape_id", "kind", "name", "note", "source", "created_by", "created_by_name", "created_at", "updated_at")},
                 "coords": json.loads(r["coords"])} for r in rows]

    def save_shape(self, workspace_id: str, data: dict[str, Any], *, user_id: str, user_name: str, is_owner: bool,
                   boundaries_locked: bool) -> dict[str, Any] | None:
        """Add, change or delete (data['deleted']) a shape. Last change wins by updated_at.
        Pasture boundaries: owner/partner only, and only while boundaries are unlocked. Lines: anyone adds; owner or creator edits."""
        shape_id = str(data.get("shape_id") or "").strip()
        if not shape_id or len(shape_id) > 64 or not all(c.isalnum() or c in "-_" for c in shape_id):
            raise ValueError("shape_id is required (letters, numbers, - and _).")
        now = _iso(utc_now())
        updated = str(data.get("updated_at") or now)[:40]
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM shapes WHERE workspace_id = ? AND shape_id = ?", (workspace_id, shape_id)).fetchone()
            kind = str(data.get("kind") or (row["kind"] if row else ""))
            if kind != "pasture" and kind not in self.LINE_KINDS:
                raise ValueError("Unknown kind of line.")
            if kind == "pasture" or (row is not None and row["kind"] == "pasture"):
                if not is_owner:
                    raise PermissionError("Only the owner or a partner can change pasture boundaries.")
                if boundaries_locked:
                    raise PermissionError("Pasture boundaries are locked. Unlock them first (owner or partner).")
            elif row is not None and not is_owner and row["created_by"] != user_id:
                raise PermissionError("Only the owner or whoever drew it can change this line.")
            if row is not None and row["updated_at"] > updated:
                return None                                     # an older edit arriving late
            if data.get("deleted"):
                if row is not None:
                    conn.execute("UPDATE shapes SET deleted = 1, updated_at = ? WHERE workspace_id = ? AND shape_id = ?", (updated, workspace_id, shape_id))
                return None
            coords = data.get("coords")
            try:
                pts = [[round(float(p[0]), 7), round(float(p[1]), 7)] for p in coords]
            except (TypeError, ValueError, IndexError):
                raise ValueError("Points must be [longitude, latitude] pairs.") from None
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in pts):
                raise ValueError("A point is out of range.")
            if kind == "pasture":
                if len(pts) >= 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                if len(pts) < 3:
                    raise ValueError("A pasture needs at least 3 corners.")
            elif len(pts) < 2:
                raise ValueError("A line needs at least 2 points.")
            if len(pts) > 5000:
                raise ValueError("Too many points (5,000 max).")
            name = str(data.get("name") or "").strip()[:80] or ("Pasture" if kind == "pasture" else "Trail")
            note = str(data.get("note") or "").strip()[:1000] or None
            source = str(data.get("source") or (row["source"] if row else "drawn"))[:20]
            if row is None:
                conn.execute("INSERT INTO shapes(shape_id, workspace_id, kind, name, note, coords, source, created_by, created_by_name, created_at, "
                             "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (shape_id, workspace_id, kind, name, note, json.dumps(pts), source, user_id, user_name, now, updated))
            else:
                conn.execute("UPDATE shapes SET kind=?, name=?, note=?, coords=?, source=?, updated_at=?, deleted=0 WHERE workspace_id=? AND shape_id=?",
                             (kind, name, note, json.dumps(pts), source, updated, workspace_id, shape_id))
            row = conn.execute("SELECT * FROM shapes WHERE workspace_id = ? AND shape_id = ?", (workspace_id, shape_id)).fetchone()
        return {**dict(row), "coords": json.loads(row["coords"])}

    def import_pastures(self, workspace_id: str, pastures: list[dict[str, Any]], *, user_id: str, user_name: str) -> int:
        """Copy the current (uploaded-file) pastures into editable shapes, keeping their ids so history stays attached."""
        now = _iso(utc_now())
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM shapes WHERE workspace_id = ? AND kind = 'pasture' AND deleted = 0", (workspace_id,)).fetchone():
                return 0
            for p in pastures:
                pts = [[round(float(x), 7), round(float(y), 7)] for x, y in p["outline"]]
                if len(pts) >= 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                sid = "".join(c for c in str(p["id"]) if c.isalnum() or c in "-_")[:64] or None
                if not sid or len(pts) < 3:
                    continue
                conn.execute("INSERT OR REPLACE INTO shapes(shape_id, workspace_id, kind, name, note, coords, source, created_by, created_by_name, "
                             "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (sid, workspace_id, "pasture", str(p["name"])[:80], None, json.dumps(pts), "imported", user_id, user_name, now, now))
        return len(pastures)

    # -- places on the map -------------------------------------------------------
    PLACE_KINDS = {
        "water_tank", "trough", "pond", "windmill", "water_other",
        "deer_blind", "feeder", "game_camera", "stand",
        "gate", "cattle_guard", "pens", "building", "mineral", "other",
        # sensors: marked now with GPS + photo; device_id links the pin to its readings once sensors are connected
        "sensor_rain", "sensor_water", "sensor_soil", "sensor_weather", "sensor_other",
    }

    def list_places(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM places WHERE workspace_id = ? AND deleted = 0 ORDER BY name", (workspace_id,)).fetchall()
        return [{k: r[k] for k in ("place_id", "kind", "name", "note", "lat", "lon", "photo_id", "device_id", "created_by", "created_by_name",
                                   "created_at", "updated_at")} for r in rows]

    def save_place(self, workspace_id: str, data: dict[str, Any], *, user_id: str, user_name: str, is_owner: bool) -> dict[str, Any]:
        """Add or change a place. Last change wins (by updated_at), so re-sending from a phone is safe."""
        place_id = str(data.get("place_id") or "").strip()
        if not place_id or len(place_id) > 64:
            raise ValueError("place_id is required.")
        kind = str(data.get("kind") or "")
        if kind not in self.PLACE_KINDS:
            raise ValueError("Unknown kind of place.")
        name = str(data.get("name") or "").strip()[:80]
        if not name:
            raise ValueError("A place needs a name.")
        try:
            lat, lon = float(data["lat"]), float(data["lon"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("A place needs a location.") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("That location isn't valid.")
        now = _iso(utc_now())
        updated = str(data.get("updated_at") or now)[:40]
        device = str(data.get("device_id") or "").strip()[:64] or None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM places WHERE place_id = ?", (place_id,)).fetchone()
            if row is not None:
                if row["workspace_id"] != workspace_id:
                    raise ValueError("place_id already used.")
                if not is_owner and row["created_by"] != user_id:
                    raise PermissionError("Only the owner or whoever added it can change a place.")
                if row["updated_at"] > updated:          # an older edit arriving late
                    return dict(row)
                conn.execute("UPDATE places SET kind=?, name=?, note=?, lat=?, lon=?, photo_id=?, device_id=?, updated_at=?, deleted=0 WHERE place_id=?",
                             (kind, name, (str(data.get("note") or "").strip()[:1000] or None), lat, lon,
                              data.get("photo_id") or row["photo_id"], device, updated, place_id))
            else:
                conn.execute("INSERT INTO places(place_id, workspace_id, kind, name, note, lat, lon, photo_id, created_by, created_by_name, "
                             "created_at, updated_at, device_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (place_id, workspace_id, kind, name, (str(data.get("note") or "").strip()[:1000] or None), lat, lon,
                              data.get("photo_id"), user_id, user_name, now, updated, device))
            return dict(conn.execute("SELECT * FROM places WHERE place_id = ?", (place_id,)).fetchone())

    def delete_place(self, workspace_id: str, place_id: str, *, user_id: str, is_owner: bool) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT created_by FROM places WHERE workspace_id = ? AND place_id = ?", (workspace_id, place_id)).fetchone()
            if row is None:
                return False
            if not is_owner and row["created_by"] != user_id:
                raise PermissionError("Only the owner or whoever added it can delete a place.")
            conn.execute("UPDATE places SET deleted = 1 WHERE place_id = ?", (place_id,))
        return True

    # -- to-do list (jobs around the ranch) --------------------------------------
    TASK_OPS = {"add", "done", "undo", "delete"}

    def list_tasks(self, workspace_id: str, done_days: int = 14) -> list[dict[str, Any]]:
        since = _iso(utc_now() - timedelta(days=done_days))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE workspace_id = ? AND deleted = 0 AND (done_at IS NULL OR done_at >= ?)",
                (workspace_id, since)).fetchall()
            history = conn.execute(
                "SELECT task_id, op, user_name, at FROM task_ops WHERE workspace_id = ? AND op IN ('done','undo') AND at >= ? ORDER BY at DESC",
                (workspace_id, since)).fetchall()
        hist: dict[str, list[dict[str, Any]]] = {}
        for h in history:
            hist.setdefault(h["task_id"], []).append({"op": h["op"], "by": h["user_name"], "at": h["at"]})
        out = []
        for r in rows:
            item = {k: r[k] for k in ("task_id", "title", "note", "pasture_id", "due_date", "repeat_days", "assignee_id", "lat", "lon",
                                      "source_id", "created_by", "created_by_name", "created_at", "done_at", "done_by", "done_by_name")}
            item["history"] = hist.get(r["task_id"], [])[:5]
            out.append(item)
        return out

    def apply_task_ops(self, workspace_id: str, ops: list[dict[str, Any]], *, user_id: str, user_name: str,
                       is_owner: bool) -> dict[str, Any]:
        """Apply to-do changes sent from phones. Each op has an op_id, so re-sending after lost signal is safe."""
        applied, errors = [], []
        for op in ops:
            op_id = str(op.get("op_id") or "").strip()
            kind = str(op.get("op") or "")
            task_id = str(op.get("task_id") or "").strip()
            try:
                if not op_id or len(op_id) > 64 or not task_id or len(task_id) > 64:
                    raise ValueError("op_id and task_id are required.")
                if kind not in self.TASK_OPS:
                    raise ValueError(f"op must be one of {sorted(self.TASK_OPS)}.")
                with self._connect() as conn:
                    if conn.execute("SELECT 1 FROM task_ops WHERE op_id = ?", (op_id,)).fetchone():
                        applied.append(op_id); continue
                    at = str(op.get("at") or _iso(utc_now()))[:40]
                    task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
                    if task is not None and task["workspace_id"] != workspace_id:
                        raise ValueError("task_id already used.")
                    prev = None
                    if kind == "add":
                        if task is None:
                            title = str(op.get("title") or "").strip()[:120]
                            if not title:
                                raise ValueError("A job needs a title.")
                            repeat = int(op.get("repeat_days") or 0)
                            if repeat not in {0, 1, 2, 3, 7, 14, 30}:
                                raise ValueError("repeat_days must be 0, 1, 2, 3, 7, 14 or 30.")
                            due = str(op.get("due_date") or "")[:10] or None
                            if due:
                                datetime.strptime(due, "%Y-%m-%d")
                            num = lambda k: float(op[k]) if op.get(k) is not None else None  # noqa: E731
                            conn.execute(
                                "INSERT INTO tasks(task_id, workspace_id, title, note, pasture_id, due_date, repeat_days, assignee_id, lat, lon, "
                                "source_id, created_by, created_by_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (task_id, workspace_id, title, (str(op.get("note") or "").strip()[:1000] or None), op.get("pasture_id"),
                                 due, repeat, op.get("assignee_id"), num("lat"), num("lon"), op.get("source_id"), user_id, user_name, at))
                    elif task is None or task["deleted"]:
                        raise ValueError("That job no longer exists.")
                    elif kind == "done":
                        if task["repeat_days"]:
                            # Repeating job: log it and move the due date on from the day it was done.
                            prev = json.dumps({"due_date": task["due_date"], "done_at": task["done_at"]})
                            next_due = (datetime.fromisoformat(at.replace("Z", "+00:00")).date() + timedelta(days=task["repeat_days"])).isoformat()
                            conn.execute("UPDATE tasks SET due_date = ? WHERE task_id = ?", (next_due, task_id))
                        elif task["done_at"] is None:
                            conn.execute("UPDATE tasks SET done_at = ?, done_by = ?, done_by_name = ? WHERE task_id = ?",
                                         (at, user_id, user_name, task_id))
                        if task["source_id"]:      # the job came from a report or photo: doing it resolves that problem
                            cur = conn.execute("SELECT resolved FROM resolutions WHERE workspace_id = ? AND item_id = ?",
                                               (workspace_id, task["source_id"])).fetchone()
                            if cur is None or not cur["resolved"]:
                                self._set_resolution(conn, workspace_id, task["source_id"], True, at, user_id, user_name,
                                                     f"Job done: {task['title']}", via_task=task_id)
                    elif kind == "undo":
                        last = conn.execute("SELECT * FROM task_ops WHERE task_id = ? AND op = 'done' ORDER BY at DESC LIMIT 1",
                                            (task_id,)).fetchone()
                        if last is None:
                            raise ValueError("Nothing to undo.")
                        if not is_owner and last["user_id"] != user_id:
                            raise PermissionError("Only the person who checked it off, or the owner, can undo it.")
                        if task["repeat_days"] and last["prev"]:
                            conn.execute("UPDATE tasks SET due_date = ? WHERE task_id = ?", (json.loads(last["prev"]).get("due_date"), task_id))
                        else:
                            conn.execute("UPDATE tasks SET done_at = NULL, done_by = NULL, done_by_name = NULL WHERE task_id = ?", (task_id,))
                        conn.execute("UPDATE task_ops SET op = 'done-undone' WHERE op_id = ?", (last["op_id"],))
                        if task["source_id"]:      # reopen the problem only if this job is what resolved it
                            cur = conn.execute("SELECT resolved, via_task FROM resolutions WHERE workspace_id = ? AND item_id = ?",
                                               (workspace_id, task["source_id"])).fetchone()
                            if cur is not None and cur["resolved"] and cur["via_task"] == task_id:
                                self._set_resolution(conn, workspace_id, task["source_id"], False, max(at, _iso(utc_now())), user_id, user_name)
                    elif kind == "delete":
                        if not is_owner and task["created_by"] != user_id:
                            raise PermissionError("Only the owner or whoever added it can delete a job.")
                        conn.execute("UPDATE tasks SET deleted = 1 WHERE task_id = ?", (task_id,))
                    conn.execute("INSERT INTO task_ops(op_id, workspace_id, task_id, op, user_id, user_name, at, prev) VALUES (?,?,?,?,?,?,?,?)",
                                 (op_id, workspace_id, task_id, kind, user_id, user_name, at, prev))
                applied.append(op_id)
            except (ValueError, PermissionError, TypeError) as exc:
                errors.append({"op_id": op_id, "error": str(exc)})
        return {"applied": applied, "errors": errors}

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
        now = utc_now()
        if row is None or row["expires_at"] < _iso(now):
            return None
        # Sliding renewal, at most once a day: a sign-in that keeps being used never runs out.
        if row["expires_at"] < _iso(now + timedelta(days=SESSION_DAYS - 1)):
            with self._connect() as conn:
                conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                             (_iso(now + timedelta(days=SESSION_DAYS)), self._hash(token)))
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
