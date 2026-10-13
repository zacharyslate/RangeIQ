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
