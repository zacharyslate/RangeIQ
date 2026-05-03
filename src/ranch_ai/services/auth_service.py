from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from ranch_ai.config import normalize_workspace_id


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8
PBKDF2_ITERATIONS = 200_000


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str
    full_name: str
    ranch_name: str
    ranch_address: str
    ranch_latitude: float | None
    ranch_longitude: float | None
    workspace_id: str
    created_at: datetime
    last_login_at: datetime | None


class AuthError(ValueError):
    """Raised when a sign-up or login validation fails."""


class AuthService:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_tables(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    ranch_name TEXT NOT NULL,
                    ranch_address TEXT NOT NULL,
                    ranch_latitude REAL,
                    ranch_longitude REAL,
                    workspace_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                )
                """
            )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise AuthError("Please enter a valid email address.")
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < PASSWORD_MIN_LENGTH:
            raise AuthError(f"Passwords must be at least {PASSWORD_MIN_LENGTH} characters long.")

    @staticmethod
    def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
        salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return salt.hex(), digest.hex()

    @classmethod
    def _verify_password(cls, password: str, *, salt_hex: str, stored_hash_hex: str) -> bool:
        _, candidate_hash = cls._hash_password(password, salt_hex=salt_hex)
        return hmac.compare_digest(candidate_hash, stored_hash_hex)

    @staticmethod
    def _workspace_id_for_email(email: str) -> str:
        slug = email.split("@", 1)[0]
        return normalize_workspace_id(f"user-{slug}-{uuid4().hex[:10]}", fallback=f"user-{uuid4().hex[:10]}")

    @staticmethod
    def _row_to_user(row: sqlite3.Row | None) -> AuthUser | None:
        if row is None:
            return None
        return AuthUser(
            user_id=str(row["user_id"]),
            email=str(row["email"]),
            full_name=str(row["full_name"]),
            ranch_name=str(row["ranch_name"]),
            ranch_address=str(row["ranch_address"]),
            ranch_latitude=float(row["ranch_latitude"]) if row["ranch_latitude"] is not None else None,
            ranch_longitude=float(row["ranch_longitude"]) if row["ranch_longitude"] is not None else None,
            workspace_id=str(row["workspace_id"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            last_login_at=datetime.fromisoformat(str(row["last_login_at"])) if row["last_login_at"] else None,
        )

    def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        ranch_name: str,
        ranch_address: str,
        ranch_latitude: float | None = None,
        ranch_longitude: float | None = None,
    ) -> AuthUser:
        normalized_email = self._normalize_email(email)
        self._validate_password(password)

        full_name = full_name.strip()
        ranch_name = ranch_name.strip()
        ranch_address = ranch_address.strip()
        if not full_name:
            raise AuthError("Please enter your name.")
        if not ranch_name:
            raise AuthError("Please enter a ranch name.")
        if not ranch_address:
            raise AuthError("Please enter a ranch address.")

        salt_hex, password_hash_hex = self._hash_password(password)
        user_id = uuid4().hex
        workspace_id = self._workspace_id_for_email(normalized_email)
        now = self._utc_now().isoformat()

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (
                        user_id,
                        email,
                        full_name,
                        password_salt,
                        password_hash,
                        ranch_name,
                        ranch_address,
                        ranch_latitude,
                        ranch_longitude,
                        workspace_id,
                        created_at,
                        last_login_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_email,
                        full_name,
                        salt_hex,
                        password_hash_hex,
                        ranch_name,
                        ranch_address,
                        ranch_latitude,
                        ranch_longitude,
                        workspace_id,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError("An account with that email already exists.") from exc

        return self.authenticate_user(email=normalized_email, password=password)

    def authenticate_user(self, *, email: str, password: str) -> AuthUser:
        normalized_email = self._normalize_email(email)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM users
                WHERE email = ?
                """,
                (normalized_email,),
            ).fetchone()

            if row is None:
                raise AuthError("No account was found for that email.")
            if not self._verify_password(password, salt_hex=str(row["password_salt"]), stored_hash_hex=str(row["password_hash"])):
                raise AuthError("Incorrect password.")

            now = self._utc_now().isoformat()
            connection.execute(
                "UPDATE users SET last_login_at = ? WHERE user_id = ?",
                (now, row["user_id"]),
            )
            refreshed = connection.execute("SELECT * FROM users WHERE user_id = ?", (row["user_id"],)).fetchone()

        user = self._row_to_user(refreshed)
        if user is None:
            raise AuthError("Unable to load the signed-in account.")
        return user

    def get_user_by_id(self, user_id: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return self._row_to_user(row)

    def get_user_by_email(self, email: str) -> AuthUser | None:
        normalized_email = self._normalize_email(email)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
        return self._row_to_user(row)

    def update_user_profile(
        self,
        user_id: str,
        *,
        full_name: str | None = None,
        ranch_name: str | None = None,
        ranch_address: str | None = None,
        ranch_latitude: float | None = None,
        ranch_longitude: float | None = None,
    ) -> AuthUser:
        current = self.get_user_by_id(user_id)
        if current is None:
            raise AuthError("User account no longer exists.")

        updated_values: dict[str, Any] = {
            "full_name": current.full_name if full_name is None else full_name.strip(),
            "ranch_name": current.ranch_name if ranch_name is None else ranch_name.strip(),
            "ranch_address": current.ranch_address if ranch_address is None else ranch_address.strip(),
            "ranch_latitude": current.ranch_latitude if ranch_latitude is None else float(ranch_latitude),
            "ranch_longitude": current.ranch_longitude if ranch_longitude is None else float(ranch_longitude),
        }

        if not updated_values["full_name"]:
            raise AuthError("Please enter your name.")
        if not updated_values["ranch_name"]:
            raise AuthError("Please enter a ranch name.")
        if not updated_values["ranch_address"]:
            raise AuthError("Please enter a ranch address.")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET full_name = ?,
                    ranch_name = ?,
                    ranch_address = ?,
                    ranch_latitude = ?,
                    ranch_longitude = ?
                WHERE user_id = ?
                """,
                (
                    updated_values["full_name"],
                    updated_values["ranch_name"],
                    updated_values["ranch_address"],
                    updated_values["ranch_latitude"],
                    updated_values["ranch_longitude"],
                    user_id,
                ),
            )

        refreshed = self.get_user_by_id(user_id)
        if refreshed is None:
            raise AuthError("Unable to reload the updated account.")
        return refreshed
