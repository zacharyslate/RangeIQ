from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ranch_ai.config import _load_yaml_or_simple_yaml, settings
from ranch_ai.data_sources.air.epa_aqs import EPAAQSDataSource
from ranch_ai.data_sources.base import BaseDataSourceProvider, PlaceholderDataSourceProvider
from ranch_ai.data_sources.cache import FileResponseCache
from ranch_ai.data_sources.drought.drought_monitor import DroughtMonitorDataSource
from ranch_ai.data_sources.fire.nasa_firms import NasaFIRMSDataSource
from ranch_ai.data_sources.land.nass_cdl import NASSCroplandDataLayerDataSource
from ranch_ai.data_sources.land.nass_quickstats import NASSQuickStatsDataSource
from ranch_ai.data_sources.land.nlcd_mrlc import NLCDMRLCDataSource
from ranch_ai.data_sources.rate_limit import ProviderRateLimiter
from ranch_ai.data_sources.satellite.planetary_computer import PlanetaryComputerDataSource
from ranch_ai.data_sources.soil.nrcs_soil_data_access import NRCSSoilDataAccessDataSource
from ranch_ai.data_sources.water.twdb import TWDBWaterDataSource
from ranch_ai.data_sources.water.usgs_water import USGSWaterDataSource
from ranch_ai.data_sources.weather.nasa_power import NasaPowerDataSource
from ranch_ai.data_sources.weather.nws import NWSDataSource
from ranch_ai.data_sources.weather.open_meteo import OpenMeteoDataSource
from ranch_ai.data_sources.weather.texmesonet import TexMesonetDataSource


PROVIDER_CLASSES: dict[str, type[BaseDataSourceProvider] | type[PlaceholderDataSourceProvider]] = {
    "nws": NWSDataSource,
    "open_meteo": OpenMeteoDataSource,
    "nasa_power": NasaPowerDataSource,
    "texmesonet": TexMesonetDataSource,
    "nrcs_soil_data_access": NRCSSoilDataAccessDataSource,
    "drought_monitor": DroughtMonitorDataSource,
    "usgs_water": USGSWaterDataSource,
    "twdb": TWDBWaterDataSource,
    "nasa_firms": NasaFIRMSDataSource,
    "nlcd_mrlc": NLCDMRLCDataSource,
    "nass_cdl": NASSCroplandDataLayerDataSource,
    "nass_quickstats": NASSQuickStatsDataSource,
    "epa_aqs": EPAAQSDataSource,
    "planetary_computer": PlanetaryComputerDataSource,
}


@dataclass
class HealthCheckReport:
    provider_count: int
    statuses: list[dict[str, Any]]

    def to_lines(self) -> list[str]:
        lines = [f"RangeIQ data source health check ({self.provider_count} providers)"]
        for status in self.statuses:
            state = "ready" if status["available"] else "not-ready"
            lines.append(
                f"- {status['name']} [{status['category']}] {state} | enabled={status['enabled']} | access={status['access_level']}"
            )
            if status.get("warning"):
                lines.append(f"  warning: {status['warning']}")
            if status.get("details"):
                lines.append(f"  details: {status['details']}")
            if status.get("required_env"):
                lines.append(f"  env: {', '.join(status['required_env'])}")
        return lines


class SourceRegistry:
    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else settings.config_dir / "api_sources.yaml"
        self.config = self._load_config(self.config_path)
        self.cache = FileResponseCache(settings.data_sources_cache_dir, enabled=True)
        self.rate_limiter = ProviderRateLimiter()
        self.providers = self._build_providers()

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"api_sources": {}}
        payload = _load_yaml_or_simple_yaml(path)
        return payload if isinstance(payload, dict) else {"api_sources": {}}

    def _provider_config(self, provider_name: str) -> dict[str, Any]:
        api_sources = self.config.get("api_sources", {})
        config = api_sources.get(provider_name, {})
        return config if isinstance(config, dict) else {}

    def _build_providers(self) -> dict[str, Any]:
        providers: dict[str, Any] = {}
        for provider_name, provider_cls in PROVIDER_CLASSES.items():
            providers[provider_name] = provider_cls(
                config=self._provider_config(provider_name),
                cache=self.cache,
                rate_limiter=self.rate_limiter,
            )
        return providers

    def get(self, provider_name: str):
        return self.providers[provider_name]

    def list_statuses(self) -> list[dict[str, Any]]:
        return [provider.get_status().to_dict() for provider in self.providers.values()]

    def health_check(self) -> HealthCheckReport:
        statuses = [provider.health_check().to_dict() for provider in self.providers.values()]
        return HealthCheckReport(provider_count=len(statuses), statuses=statuses)

    def fetch_point(self, provider_name: str, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        return self.get(provider_name).fetch_point(latitude, longitude, **kwargs)

    def fetch_area(self, provider_name: str, bbox: tuple[float, float, float, float], **kwargs: Any) -> dict[str, Any]:
        return self.get(provider_name).fetch_area(bbox, **kwargs)


def build_default_registry(config_path: str | Path | None = None) -> SourceRegistry:
    return SourceRegistry(config_path=config_path)


def run_health_check(config_path: str | Path | None = None) -> HealthCheckReport:
    registry = build_default_registry(config_path=config_path)
    return registry.health_check()
