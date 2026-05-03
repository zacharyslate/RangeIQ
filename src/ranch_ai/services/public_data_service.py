from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.data.public_sources import (
    NASA_POWER_CITATION_URL,
    USDA_SDA_CITATION_URL,
    USDM_CITATION_URL,
    MockDroughtHistoryProvider,
    MockHistoricalWeatherProvider,
    MockSoilProfileProvider,
    NasaPowerHistoricalWeatherProvider,
    USDASoilDataAccessProvider,
    USDroughtMonitorProvider,
)
from ranch_ai.models.public_data_schema import PublicDataBundle, PublicSourceStatus
from ranch_ai.services.public_data_cache import PublicDataCache
from ranch_ai.vegetation.vegetation_service import VegetationService


def _history_provider_from_name(provider_name: str, app_settings: Settings):
    if provider_name == "nasa_power":
        return NasaPowerHistoricalWeatherProvider(timeout_seconds=app_settings.public_data.historical_weather.timeout_seconds)
    return MockHistoricalWeatherProvider(seed=app_settings.random_seed)


def _soil_provider_from_name(provider_name: str, app_settings: Settings):
    if provider_name == "usda_sda":
        return USDASoilDataAccessProvider(timeout_seconds=app_settings.public_data.soils.timeout_seconds)
    return MockSoilProfileProvider(seed=app_settings.random_seed)


def _drought_provider_from_name(provider_name: str, app_settings: Settings):
    if provider_name == "usdm":
        return USDroughtMonitorProvider(timeout_seconds=app_settings.public_data.drought.timeout_seconds)
    return MockDroughtHistoryProvider(seed=app_settings.random_seed)


class PublicDataService:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings
        self.cache = PublicDataCache(
            cache_dir=self.settings.public_data_cache_dir,
            enabled=self.settings.public_data.cache_enabled,
        )

    @staticmethod
    def _cache_context_dates(start_date: str | pd.Timestamp, end_date: str | pd.Timestamp) -> dict[str, str]:
        return {
            "start_date": pd.Timestamp(start_date).strftime("%Y-%m-%d"),
            "end_date": pd.Timestamp(end_date).strftime("%Y-%m-%d"),
        }

    @staticmethod
    def _pasture_cache_context(pastures: pd.DataFrame) -> list[dict[str, Any]]:
        fields = ["pasture_id", "centroid_lat", "centroid_lon", "acres"]
        frame = pastures[[field for field in fields if field in pastures.columns]].copy()
        records = frame.to_dict(orient="records")
        return [
            {
                **record,
                "centroid_lat": round(float(record["centroid_lat"]), 6) if record.get("centroid_lat") is not None else None,
                "centroid_lon": round(float(record["centroid_lon"]), 6) if record.get("centroid_lon") is not None else None,
                "acres": round(float(record["acres"]), 4) if record.get("acres") is not None else None,
            }
            for record in records
        ]

    def _status_from_cache(
        self,
        *,
        component: str,
        configured_provider: str,
        active_provider: str,
        citation_url: str,
        loaded_at: pd.Timestamp,
        message: str,
        mode: str,
        cached_frame,
    ) -> PublicSourceStatus:
        return PublicSourceStatus(
            component=component,
            configured_provider=configured_provider,
            active_provider=active_provider,
            mode=mode,
            status=message,
            citation_url=citation_url,
            loaded_at=loaded_at,
            cache_path=str(cached_frame.data_path),
            cache_saved_at=cached_frame.saved_at.tz_localize(None) if cached_frame.saved_at.tzinfo else cached_frame.saved_at,
            cache_expires_at=(
                cached_frame.expires_at.tz_localize(None) if cached_frame.expires_at is not None and cached_frame.expires_at.tzinfo else cached_frame.expires_at
            ),
            cache_age_hours=cached_frame.age_hours,
        )

    def _status_without_cache(
        self,
        *,
        component: str,
        configured_provider: str,
        active_provider: str,
        citation_url: str,
        loaded_at: pd.Timestamp,
        message: str,
        mode: str,
        cached_frame=None,
    ) -> PublicSourceStatus:
        return PublicSourceStatus(
            component=component,
            configured_provider=configured_provider,
            active_provider=active_provider,
            mode=mode,
            status=message,
            citation_url=citation_url,
            loaded_at=loaded_at,
            cache_path=str(cached_frame.data_path) if cached_frame is not None else None,
            cache_saved_at=(
                cached_frame.saved_at.tz_localize(None) if cached_frame is not None and cached_frame.saved_at.tzinfo else getattr(cached_frame, "saved_at", None)
            ),
            cache_expires_at=(
                cached_frame.expires_at.tz_localize(None)
                if cached_frame is not None and getattr(cached_frame, "expires_at", None) is not None and cached_frame.expires_at.tzinfo
                else getattr(cached_frame, "expires_at", None)
            ),
            cache_age_hours=getattr(cached_frame, "age_hours", None),
        )

    def _load_component_with_cache(
        self,
        *,
        component: str,
        configured_provider: str,
        provider: Any,
        fetcher: Callable[[], pd.DataFrame],
        fallback_fetcher: Callable[[], pd.DataFrame],
        refresh_hours: int | float,
        citation_url: str,
        loaded_at: pd.Timestamp,
        cache_context: dict[str, Any],
        real_message: str,
        fallback_message_prefix: str,
    ) -> tuple[pd.DataFrame, PublicSourceStatus]:
        if provider.provider_name == "mock":
            frame = fetcher()
            return frame, self._status_without_cache(
                component=component,
                configured_provider=configured_provider,
                active_provider=provider.provider_name,
                citation_url=citation_url,
                loaded_at=loaded_at,
                message=real_message,
                mode="mock",
            )

        cached_frame = self.cache.load(component, provider.provider_name, cache_context)
        if cached_frame is not None and cached_frame.is_fresh:
            return cached_frame.frame, self._status_from_cache(
                component=component,
                configured_provider=configured_provider,
                active_provider=provider.provider_name,
                citation_url=citation_url,
                loaded_at=loaded_at,
                message=f"Using cached {provider.provider_name} {component.lower()} data.",
                mode="cached",
                cached_frame=cached_frame,
            )

        try:
            frame = fetcher()
            saved_cache = self.cache.save(
                component=component,
                provider_name=provider.provider_name,
                context=cache_context,
                frame=frame,
                refresh_hours=refresh_hours,
            )
            return frame, self._status_without_cache(
                component=component,
                configured_provider=configured_provider,
                active_provider=provider.provider_name,
                citation_url=citation_url,
                loaded_at=loaded_at,
                message=real_message,
                mode="real",
                cached_frame=saved_cache,
            )
        except Exception as exc:
            if cached_frame is not None:
                return cached_frame.frame, self._status_from_cache(
                    component=component,
                    configured_provider=configured_provider,
                    active_provider=provider.provider_name,
                    citation_url=citation_url,
                    loaded_at=loaded_at,
                    message=(
                        f"{configured_provider} refresh failed; using cached {component.lower()} data instead. {exc}"
                    ),
                    mode="stale-cache",
                    cached_frame=cached_frame,
                )

            frame = fallback_fetcher()
            return frame, self._status_without_cache(
                component=component,
                configured_provider=configured_provider,
                active_provider="mock",
                citation_url=citation_url,
                loaded_at=loaded_at,
                message=f"{fallback_message_prefix} {exc}",
                mode="fallback-mock" if configured_provider != "mock" else "mock",
            )

    def load_public_data_bundle(
        self,
        pastures: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        history_years: int | None = None,
    ) -> PublicDataBundle:
        lat = float(pastures["centroid_lat"].mean())
        lon = float(pastures["centroid_lon"].mean())
        loaded_at = pd.Timestamp.now()
        source_status: list[PublicSourceStatus] = []
        date_context = self._cache_context_dates(start_date, end_date)
        pasture_context = self._pasture_cache_context(pastures)

        history_provider_name = self.settings.public_data.historical_weather.provider.lower()
        history_provider = _history_provider_from_name(history_provider_name, self.settings)
        history_fallback = MockHistoricalWeatherProvider(seed=self.settings.random_seed)
        historical_weather, history_status = self._load_component_with_cache(
            component="Historical Weather",
            configured_provider=history_provider_name,
            provider=history_provider,
            fetcher=lambda: history_provider.get_daily_history(lat, lon, start_date, end_date),
            fallback_fetcher=lambda: history_fallback.get_daily_history(lat, lon, start_date, end_date),
            refresh_hours=self.settings.public_data.historical_weather.refresh_hours,
            citation_url=getattr(history_provider, "citation_url", NASA_POWER_CITATION_URL),
            loaded_at=loaded_at,
            cache_context={
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                **date_context,
            },
            real_message=f"Using {history_provider.provider_name} historical weather data.",
            fallback_message_prefix=f"{history_provider_name} historical weather unavailable; using mock data.",
        )
        source_status.append(history_status)

        soil_provider_name = self.settings.public_data.soils.provider.lower()
        soil_provider = _soil_provider_from_name(soil_provider_name, self.settings)
        soil_fallback = MockSoilProfileProvider(seed=self.settings.random_seed)
        soils, soil_status = self._load_component_with_cache(
            component="Soils",
            configured_provider=soil_provider_name,
            provider=soil_provider,
            fetcher=lambda: soil_provider.get_pasture_soils(pastures),
            fallback_fetcher=lambda: soil_fallback.get_pasture_soils(pastures),
            refresh_hours=self.settings.public_data.soils.refresh_hours,
            citation_url=getattr(soil_provider, "citation_url", USDA_SDA_CITATION_URL),
            loaded_at=loaded_at,
            cache_context={"pastures": pasture_context},
            real_message=f"Using {soil_provider.provider_name} soil profiles.",
            fallback_message_prefix=f"{soil_provider_name} soils unavailable; using mock soil profiles.",
        )
        source_status.append(soil_status)

        drought_provider_name = self.settings.public_data.drought.provider.lower()
        drought_provider = _drought_provider_from_name(drought_provider_name, self.settings)
        drought_fallback = MockDroughtHistoryProvider(seed=self.settings.random_seed)
        drought, drought_status = self._load_component_with_cache(
            component="Drought",
            configured_provider=drought_provider_name,
            provider=drought_provider,
            fetcher=lambda: drought_provider.get_weekly_drought(lat, lon, start_date, end_date),
            fallback_fetcher=lambda: drought_fallback.get_weekly_drought(lat, lon, start_date, end_date),
            refresh_hours=self.settings.public_data.drought.refresh_hours,
            citation_url=getattr(drought_provider, "citation_url", USDM_CITATION_URL),
            loaded_at=loaded_at,
            cache_context={
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                **date_context,
            },
            real_message=f"Using {drought_provider.provider_name} drought history.",
            fallback_message_prefix=f"{drought_provider_name} drought history unavailable; using mock drought data.",
        )
        source_status.append(drought_status)

        vegetation_service = VegetationService(self.settings)
        vegetation_artifacts, vegetation_statuses = vegetation_service.build_artifacts(
            pastures,
            start_date=start_date,
            end_date=end_date,
            history_years=history_years,
        )
        vegetation = vegetation_artifacts.monthly_features
        source_status.extend(vegetation_statuses)

        return PublicDataBundle(
            historical_weather=historical_weather,
            soils=soils,
            drought=drought,
            vegetation=vegetation,
            vegetation_artifacts=vegetation_artifacts,
            source_status=source_status,
            loaded_at=loaded_at,
        )

    @staticmethod
    def status_as_dicts(bundle: PublicDataBundle) -> list[dict[str, object]]:
        return [asdict(status) for status in bundle.source_status]
