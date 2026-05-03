from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class CachedPayload:
    payload: Any
    path: Path
    saved_at: pd.Timestamp
    expires_at: pd.Timestamp | None
    context: dict[str, Any]

    @property
    def is_fresh(self) -> bool:
        return self.expires_at is None or self.expires_at >= pd.Timestamp.now(tz="UTC")


class FileResponseCache:
    def __init__(self, cache_dir: Path, enabled: bool = True):
        self.cache_dir = cache_dir
        self.enabled = enabled

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): FileResponseCache._normalize(val) for key, val in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [FileResponseCache._normalize(item) for item in value]
        return value

    def _key(self, namespace: str, context: dict[str, Any]) -> str:
        payload = {
            "namespace": namespace,
            "context": self._normalize(context),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _path(self, namespace: str, context: dict[str, Any]) -> Path:
        key = self._key(namespace, context)
        return self.cache_dir / namespace / f"{key}.json"

    def load(self, namespace: str, context: dict[str, Any]) -> CachedPayload | None:
        if not self.enabled:
            return None

        path = self._path(namespace, context)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        return CachedPayload(
            payload=payload.get("payload"),
            path=path,
            saved_at=pd.Timestamp(payload["saved_at"]),
            expires_at=pd.Timestamp(payload["expires_at"]) if payload.get("expires_at") else None,
            context=payload.get("context", {}),
        )

    def save(
        self,
        namespace: str,
        context: dict[str, Any],
        payload: Any,
        ttl_hours: float | int | None = None,
    ) -> CachedPayload | None:
        if not self.enabled:
            return None

        path = self._path(namespace, context)
        path.parent.mkdir(parents=True, exist_ok=True)
        saved_at = pd.Timestamp.now(tz="UTC")
        expires_at = saved_at + pd.to_timedelta(float(ttl_hours), unit="h") if ttl_hours is not None else None
        serialized = {
            "saved_at": saved_at.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
            "context": self._normalize(context),
            "payload": payload,
        }
        path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        return CachedPayload(
            payload=payload,
            path=path,
            saved_at=saved_at,
            expires_at=expires_at,
            context=serialized["context"],
        )
