from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _normalize_geojson_input(aoi_geojson: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(aoi_geojson, dict):
        raise ValueError("AOI must be a GeoJSON dictionary.")

    if aoi_geojson.get("type") == "Feature":
        geometry = aoi_geojson.get("geometry")
        properties = aoi_geojson.get("properties", {})
    else:
        geometry = aoi_geojson
        properties = {}

    if not isinstance(geometry, dict):
        raise ValueError("GeoJSON AOI must include a geometry object.")
    if geometry.get("type") != "Polygon":
        raise ValueError("RangeIQ vegetation history currently supports Polygon AOIs only.")

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
        raise ValueError("GeoJSON polygon coordinates are missing or invalid.")

    ring = coordinates[0]
    if len(ring) < 4:
        raise ValueError("GeoJSON polygon must include at least four coordinate pairs including closure.")

    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": coordinates},
        "properties": properties if isinstance(properties, dict) else {},
    }


def _round_nested(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [_round_nested(item, digits=digits) for item in value]
    if isinstance(value, dict):
        return {str(key): _round_nested(val, digits=digits) for key, val in sorted(value.items())}
    return value


def hash_aoi_geometry(aoi_geojson: dict[str, Any]) -> str:
    normalized = _normalize_geojson_input(aoi_geojson)
    geometry_payload = _round_nested(normalized["geometry"])
    raw = json.dumps(geometry_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


@dataclass
class CachedVegetationResponse:
    normalized_payload: dict[str, Any]
    raw_payload: Any | None
    cache_key: str
    normalized_path: Path
    raw_path: Path | None
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


class VegetationCache:
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
            return {str(key): VegetationCache._normalize_context(val) for key, val in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [VegetationCache._normalize_context(item) for item in value]
        return value

    def build_cache_key(self, component: str, provider_name: str, context: dict[str, Any]) -> str:
        payload = {
            "component": component,
            "provider": provider_name,
            "context": self._normalize_context(context),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _paths(self, component: str, provider_name: str, cache_key: str) -> tuple[Path, Path, Path]:
        base_dir = self.cache_dir / component.lower().replace(" ", "_") / provider_name.lower()
        return (
            base_dir / f"{cache_key}.normalized.json",
            base_dir / f"{cache_key}.raw.json",
            base_dir / f"{cache_key}.meta.json",
        )

    def load(self, component: str, provider_name: str, context: dict[str, Any]) -> CachedVegetationResponse | None:
        if not self.enabled:
            return None

        cache_key = self.build_cache_key(component, provider_name, context)
        normalized_path, raw_path, meta_path = self._paths(component, provider_name, cache_key)
        if not normalized_path.exists() or not meta_path.exists():
            return None

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        raw_payload = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else None
        saved_at = pd.Timestamp(metadata["saved_at"])
        expires_at = pd.Timestamp(metadata["expires_at"]) if metadata.get("expires_at") else None
        return CachedVegetationResponse(
            normalized_payload=normalized_payload,
            raw_payload=raw_payload,
            cache_key=cache_key,
            normalized_path=normalized_path,
            raw_path=raw_path if raw_path.exists() else None,
            meta_path=meta_path,
            saved_at=saved_at,
            expires_at=expires_at,
            context=metadata.get("context", {}),
        )

    def save(
        self,
        *,
        component: str,
        provider_name: str,
        context: dict[str, Any],
        normalized_payload: dict[str, Any],
        raw_payload: Any | None,
        refresh_hours: int | float | None,
    ) -> CachedVegetationResponse | None:
        if not self.enabled:
            return None

        cache_key = self.build_cache_key(component, provider_name, context)
        normalized_path, raw_path, meta_path = self._paths(component, provider_name, cache_key)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        saved_at = pd.Timestamp.now(tz="UTC")
        expires_at = None
        if refresh_hours is not None:
            expires_at = saved_at + pd.to_timedelta(float(refresh_hours), unit="h")

        normalized_context = self._normalize_context(context)
        normalized_path.write_text(json.dumps(normalized_payload, indent=2), encoding="utf-8")

        if raw_payload is not None:
            try:
                raw_path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")
            except TypeError:
                raw_path = None
        else:
            raw_path = None

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

        return CachedVegetationResponse(
            normalized_payload=normalized_payload,
            raw_payload=raw_payload,
            cache_key=cache_key,
            normalized_path=normalized_path,
            raw_path=raw_path,
            meta_path=meta_path,
            saved_at=saved_at,
            expires_at=expires_at,
            context=normalized_context,
        )
