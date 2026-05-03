from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class CachedFrame:
    frame: pd.DataFrame
    cache_key: str
    data_path: Path
    meta_path: Path
    saved_at: pd.Timestamp
    expires_at: pd.Timestamp | None
    context: dict[str, Any]

    @property
    def age_hours(self) -> float:
        return round((pd.Timestamp.now(tz="UTC") - self.saved_at).total_seconds() / 3600.0, 2)

    @property
    def is_fresh(self) -> bool:
        return self.expires_at is not None and self.expires_at >= pd.Timestamp.now(tz="UTC")


class PublicDataCache:
    def __init__(self, cache_dir: Path, enabled: bool = True):
        self.cache_dir = cache_dir
        self.enabled = enabled

    @staticmethod
    def _normalize_context(value: Any) -> Any:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): PublicDataCache._normalize_context(val) for key, val in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [PublicDataCache._normalize_context(item) for item in value]
        return value

    def build_cache_key(self, component: str, provider_name: str, context: dict[str, Any]) -> str:
        payload = {
            "component": component,
            "provider": provider_name,
            "context": self._normalize_context(context),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _paths(self, component: str, provider_name: str, cache_key: str) -> tuple[Path, Path]:
        base_dir = self.cache_dir / component.lower().replace(" ", "_") / provider_name.lower()
        return base_dir / f"{cache_key}.json", base_dir / f"{cache_key}.meta.json"

    def load(self, component: str, provider_name: str, context: dict[str, Any]) -> CachedFrame | None:
        if not self.enabled:
            return None

        cache_key = self.build_cache_key(component, provider_name, context)
        data_path, meta_path = self._paths(component, provider_name, cache_key)
        if not data_path.exists() or not meta_path.exists():
            return None

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        frame = pd.read_json(io.StringIO(data_path.read_text(encoding="utf-8")), orient="table")
        saved_at = pd.Timestamp(metadata["saved_at"])
        expires_at = pd.Timestamp(metadata["expires_at"]) if metadata.get("expires_at") else None
        return CachedFrame(
            frame=frame,
            cache_key=cache_key,
            data_path=data_path,
            meta_path=meta_path,
            saved_at=saved_at,
            expires_at=expires_at,
            context=metadata.get("context", {}),
        )

    def save(
        self,
        component: str,
        provider_name: str,
        context: dict[str, Any],
        frame: pd.DataFrame,
        refresh_hours: int | float | None,
    ) -> CachedFrame | None:
        if not self.enabled:
            return None

        cache_key = self.build_cache_key(component, provider_name, context)
        data_path, meta_path = self._paths(component, provider_name, cache_key)
        data_path.parent.mkdir(parents=True, exist_ok=True)

        saved_at = pd.Timestamp.now(tz="UTC")
        expires_at = None
        if refresh_hours is not None:
            expires_at = saved_at + pd.to_timedelta(float(refresh_hours), unit="h")

        normalized_context = self._normalize_context(context)
        data_path.write_text(frame.to_json(orient="table", date_format="iso"), encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "component": component,
                    "provider": provider_name,
                    "cache_key": cache_key,
                    "saved_at": saved_at.isoformat(),
                    "expires_at": expires_at.isoformat() if expires_at is not None else None,
                    "context": normalized_context,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return CachedFrame(
            frame=frame,
            cache_key=cache_key,
            data_path=data_path,
            meta_path=meta_path,
            saved_at=saved_at,
            expires_at=expires_at,
            context=normalized_context,
        )
