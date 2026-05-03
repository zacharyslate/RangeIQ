from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.data.weather import MockWeatherProvider, NWSWeatherProvider, OpenMeteoWeatherProvider
from ranch_ai.models.weather_schema import WeatherBundle, WeatherCurrent


def _provider_from_name(provider_name: str, app_settings: Settings):
    active = provider_name.lower()
    if active == "nws":
        return NWSWeatherProvider(
            user_agent=app_settings.weather.user_agent,
            timeout_seconds=app_settings.weather.timeout_seconds,
        )
    if active == "openmeteo":
        return OpenMeteoWeatherProvider(timeout_seconds=app_settings.weather.timeout_seconds)
    return MockWeatherProvider(seed=app_settings.random_seed)


class WeatherService:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings

    def load_weather_bundle(
        self,
        lat: float,
        lon: float,
        provider: str | None = None,
    ) -> WeatherBundle:
        provider_name = (provider or self.settings.weather.provider).lower()
        active_provider = _provider_from_name(provider_name, self.settings)
        loaded_at = pd.Timestamp.now()

        try:
            current_payload = active_provider.get_current_weather(lat, lon)
            forecast_df = active_provider.get_7day_forecast(lat, lon)
            hourly_df = active_provider.get_hourly_forecast(lat, lon, hours=48)
            mode = "real" if provider_name in {"nws", "openmeteo"} else "mock"
            source_message = f"Using {active_provider.provider_name} weather provider."
        except Exception:
            fallback_provider = MockWeatherProvider(seed=self.settings.random_seed)
            current_payload = fallback_provider.get_current_weather(lat, lon)
            forecast_df = fallback_provider.get_7day_forecast(lat, lon)
            hourly_df = fallback_provider.get_hourly_forecast(lat, lon, hours=48)
            mode = "fallback-mock" if provider_name != "mock" else "mock"
            source_message = f"{provider_name} weather provider unavailable; using mock weather."
            active_provider = fallback_provider

        current = WeatherCurrent(
            observation_time=pd.to_datetime(current_payload["observation_time"]),
            temperature_f=current_payload.get("temperature_f"),
            feels_like_f=current_payload.get("feels_like_f"),
            humidity_pct=current_payload.get("humidity_pct"),
            wind_speed_mph=current_payload.get("wind_speed_mph"),
            wind_gust_mph=current_payload.get("wind_gust_mph"),
            wind_direction_deg=current_payload.get("wind_direction_deg"),
            wind_direction=current_payload.get("wind_direction"),
            precip_probability_pct=current_payload.get("precip_probability_pct"),
            rainfall_expected_today_in=current_payload.get("rainfall_expected_today_in"),
            weather_code=current_payload.get("weather_code"),
            weather_label=current_payload.get("weather_label", "Weather"),
            source=current_payload.get("source", active_provider.provider_name),
        )

        return WeatherBundle(
            current=current,
            forecast=forecast_df,
            hourly=hourly_df,
            provider_name=active_provider.provider_name,
            mode=mode,
            source_message=source_message,
            loaded_at=loaded_at,
        )

    @staticmethod
    def current_as_dict(bundle: WeatherBundle) -> dict[str, object]:
        return asdict(bundle.current)


def get_current_weather(lat: float, lon: float, provider: str | None = None, app_settings: Settings = settings) -> dict[str, object]:
    service = WeatherService(app_settings=app_settings)
    bundle = service.load_weather_bundle(lat=lat, lon=lon, provider=provider)
    return service.current_as_dict(bundle)


def get_7day_forecast(lat: float, lon: float, provider: str | None = None, app_settings: Settings = settings) -> pd.DataFrame:
    service = WeatherService(app_settings=app_settings)
    return service.load_weather_bundle(lat=lat, lon=lon, provider=provider).forecast


def get_hourly_forecast(
    lat: float,
    lon: float,
    provider: str | None = None,
    app_settings: Settings = settings,
) -> pd.DataFrame:
    service = WeatherService(app_settings=app_settings)
    return service.load_weather_bundle(lat=lat, lon=lon, provider=provider).hourly
