from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import logging
import os
import time
from typing import Any

import pandas as pd
import requests

from ranch_ai.data_sources.cache import FileResponseCache
from ranch_ai.data_sources.rate_limit import ProviderRateLimiter


LOGGER = logging.getLogger(__name__)


@dataclass
class NormalizedSourceResponse:
    source: str
    category: str
    timestamp: str
    latitude: float | None
    longitude: float | None
    data: dict[str, Any]
    units: dict[str, Any] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderStatus:
    name: str
    category: str
    enabled: bool
    requires_key: bool
    access_level: str
    commercial_safe: bool
    available: bool
    required_env: list[str] = field(default_factory=list)
    warning: str | None = None
    citation_url: str | None = None
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DataSourceError(RuntimeError):
    pass


class PlaceholderDataSourceProvider(ABC):
    name = "placeholder"
    category = "general"
    requires_key = False
    access_level = "scaffold_only"
    commercial_safe = True
    citation_url = ""

    def __init__(self, config: dict[str, Any] | None = None, **kwargs: Any):
        self.config = config or {}

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            category=self.category,
            enabled=bool(self.config.get("enabled", False)),
            requires_key=self.requires_key,
            access_level=self.access_level,
            commercial_safe=self.commercial_safe,
            available=False,
            required_env=self.required_env_names(),
            warning=self.config.get("warning") or "Provider scaffold only.",
            citation_url=self.citation_url,
            details="Not implemented yet in the free/open provider layer.",
        )

    def health_check(self) -> ProviderStatus:
        return self.get_status()

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        return {
            "source": self.name,
            "category": self.category,
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "data": {},
            "units": {},
            "raw_metadata": {"implemented": False},
            "warnings": [self.config.get("warning") or "Provider scaffold only."],
        }

    def fetch_area(self, bbox: tuple[float, float, float, float], **kwargs: Any) -> dict[str, Any]:
        west, south, east, north = bbox
        return self.fetch_point((south + north) / 2, (west + east) / 2, **kwargs)

    def normalize_response(self, raw: Any) -> dict[str, Any]:
        return raw if isinstance(raw, dict) else {"raw": raw}

    def required_env_names(self) -> list[str]:
        names = []
        for key_name in ("key_env", "optional_key_env"):
            value = self.config.get(key_name)
            if value:
                names.append(str(value))
        return names


class BaseDataSourceProvider(ABC):
    name = "base"
    category = "general"
    requires_key = False
    access_level = "free_open_government"
    commercial_safe = True
    citation_url = ""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        cache: FileResponseCache | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
        session: requests.Session | None = None,
    ):
        self.config = config or {}
        self.cache = cache
        self.rate_limiter = rate_limiter or ProviderRateLimiter()
        self.session = session or requests.Session()
        self.timeout_seconds = float(self.config.get("timeout_seconds", 10))
        self.retries = int(self.config.get("retries", 2))
        self.backoff_seconds = float(self.config.get("backoff_seconds", 0.5))
        self.rate_limit_seconds = float(self.config.get("rate_limit_seconds", 0.25))
        self.cache_ttl_hours = self.config.get("ttl_hours", 6)

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def key_env_name(self) -> str | None:
        value = self.config.get("key_env")
        return str(value) if value else None

    def optional_key_env_name(self) -> str | None:
        value = self.config.get("optional_key_env")
        return str(value) if value else None

    def required_env_names(self) -> list[str]:
        names = []
        for key_name in (self.key_env_name(), self.optional_key_env_name()):
            if key_name:
                names.append(key_name)
        return names

    def configured_key(self) -> str | None:
        key_env = self.key_env_name()
        if key_env:
            value = os.getenv(key_env, "").strip()
            if value:
                return value

        optional_env = self.optional_key_env_name()
        if optional_env:
            value = os.getenv(optional_env, "").strip()
            if value:
                return value

        configured_value = str(self.config.get("api_key", "")).strip()
        return configured_value or None

    def _default_warning(self) -> str | None:
        warning = self.config.get("warning")
        if warning:
            return str(warning)
        if not self.commercial_safe:
            return "Development/research only unless production licensing is resolved."
        return None

    def _base_status(self) -> ProviderStatus:
        details = None
        available = self.enabled
        if not self.enabled:
            details = "Provider disabled in config/api_sources.yaml."
        elif self.requires_key and not self.configured_key():
            available = False
            details = "Required credential is not configured."
        return ProviderStatus(
            name=self.name,
            category=self.category,
            enabled=self.enabled,
            requires_key=self.requires_key,
            access_level=str(self.config.get("access_level", self.access_level)),
            commercial_safe=bool(self.config.get("commercial_safe", self.commercial_safe)),
            available=available,
            required_env=self.required_env_names(),
            warning=self._default_warning(),
            citation_url=self.config.get("citation_url") or self.citation_url,
            details=details,
        )

    def get_status(self) -> ProviderStatus:
        return self._base_status()

    def health_check(self) -> ProviderStatus:
        return self.get_status()

    def _response(
        self,
        *,
        latitude: float | None,
        longitude: float | None,
        data: dict[str, Any],
        units: dict[str, Any] | None = None,
        raw_metadata: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = NormalizedSourceResponse(
            source=self.name,
            category=self.category,
            timestamp=pd.Timestamp.now(tz="UTC").isoformat(),
            latitude=latitude,
            longitude=longitude,
            data=data,
            units=units or {},
            raw_metadata=raw_metadata or {},
            warnings=warnings or [],
        )
        return payload.to_dict()

    def _disabled_response(self, latitude: float | None, longitude: float | None, message: str) -> dict[str, Any]:
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={},
            raw_metadata={"enabled": self.enabled},
            warnings=[message],
        )

    def _request_json(
        self,
        *,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        cache_context: dict[str, Any] | None = None,
        cache_ttl_hours: float | int | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        params = params or {}
        headers = headers or {}
        namespace = self.name
        context = {
            "method": method,
            "url": url,
            "params": params,
            **(cache_context or {}),
        }
        if self.cache is not None:
            cached = self.cache.load(namespace, context)
            if cached is not None and cached.is_fresh:
                return cached.payload, {"cache_hit": True, "stale_cache": False}
        else:
            cached = None

        if self.rate_limiter is not None:
            self.rate_limiter.wait(self.name, self.rate_limit_seconds)

        last_exc: Exception | None = None
        request_func = self.session.request
        for attempt in range(self.retries + 1):
            try:
                response = request_func(method, url, params=params, headers=headers, timeout=self.timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                if self.cache is not None:
                    self.cache.save(namespace, context, payload, ttl_hours=cache_ttl_hours or self.cache_ttl_hours)
                return payload, {"cache_hit": False, "stale_cache": False}
            except Exception as exc:  # pragma: no cover - exercised via public provider tests
                last_exc = exc
                LOGGER.warning("Provider %s request failed on attempt %s: %s", self.name, attempt + 1, exc)
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))

        if cached is not None:
            LOGGER.warning("Provider %s request failed; using stale cached payload.", self.name)
            return cached.payload, {"cache_hit": True, "stale_cache": True}

        raise DataSourceError(str(last_exc) if last_exc is not None else "Unknown provider request failure.")

    @abstractmethod
    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def fetch_area(self, bbox: tuple[float, float, float, float], **kwargs: Any) -> dict[str, Any]:
        west, south, east, north = bbox
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2
        response = self.fetch_point(center_lat, center_lon, **kwargs)
        response["warnings"].append("Area fetch is approximated with the bbox centroid in this MVP provider.")
        response["raw_metadata"]["bbox"] = {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        }
        return response

    @abstractmethod
    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
