from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.data.weather import celsius_to_fahrenheit, mm_to_inches, parse_wind_speed_text
from ranch_ai.data_sources.base import BaseDataSourceProvider


def _convert_value(payload: dict[str, Any] | None, kind: str) -> float | None:
    if not payload:
        return None
    value = payload.get("value")
    if value is None:
        return None
    unit = str(payload.get("unitCode", ""))
    numeric = float(value)
    if kind == "temperature" and "degC" in unit:
        return celsius_to_fahrenheit(numeric)
    if kind == "precipitation" and "mm" in unit:
        return mm_to_inches(numeric)
    if kind == "wind" and "m_s" in unit:
        return numeric * 2.23694
    return numeric


class NWSDataSource(BaseDataSourceProvider):
    name = "nws"
    category = "weather"
    requires_key = False
    access_level = "free_open_government"
    commercial_safe = True
    citation_url = "https://www.weather.gov/documentation/services-web-api"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "NWS is disabled in config/api_sources.yaml.")

        headers = {
            "Accept": self.config.get("accept", "application/geo+json"),
            "User-Agent": self.config.get("user_agent", "RangeIQ/0.1 (contact@example.com)"),
        }
        warnings: list[str] = []
        try:
            point_payload, point_meta = self._request_json(
                url=f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}",
                headers=headers,
                cache_context={"kind": "point-lookup", "latitude": round(latitude, 4), "longitude": round(longitude, 4)},
                cache_ttl_hours=12,
            )
            properties = point_payload.get("properties", {})
            forecast_url = properties.get("forecast")
            hourly_url = properties.get("forecastHourly")
            stations_url = properties.get("observationStations")
            latest_station = None
            latest_observation = {}

            if stations_url:
                stations_payload, _ = self._request_json(
                    url=stations_url,
                    headers=headers,
                    cache_context={"kind": "stations", "latitude": round(latitude, 4), "longitude": round(longitude, 4)},
                    cache_ttl_hours=12,
                )
                features = stations_payload.get("features", [])
                if features:
                    latest_station = features[0]
                    station_id = latest_station.get("id")
                    if station_id:
                        observation_url = f"{station_id}/observations/latest"
                        try:
                            observation_payload, observation_meta = self._request_json(
                                url=observation_url,
                                headers=headers,
                                cache_context={"kind": "latest-observation", "station_id": station_id},
                                cache_ttl_hours=0.5,
                            )
                            latest_observation = observation_payload.get("properties", {})
                            if observation_meta.get("stale_cache"):
                                warnings.append("Using stale cached NWS station observation because the live request failed.")
                        except Exception as exc:
                            warnings.append(f"NWS latest observation unavailable: {exc}")

            forecast_periods = []
            if forecast_url:
                forecast_payload, forecast_meta = self._request_json(
                    url=forecast_url,
                    headers=headers,
                    cache_context={"kind": "forecast", "url": forecast_url},
                    cache_ttl_hours=1,
                )
                forecast_periods = (forecast_payload.get("properties", {}) or {}).get("periods", [])[:7]
                if forecast_meta.get("stale_cache"):
                    warnings.append("Using stale cached NWS daily forecast because the live request failed.")

            hourly_periods = []
            if hourly_url:
                hourly_payload, hourly_meta = self._request_json(
                    url=hourly_url,
                    headers=headers,
                    cache_context={"kind": "hourly", "url": hourly_url},
                    cache_ttl_hours=1,
                )
                hourly_periods = (hourly_payload.get("properties", {}) or {}).get("periods", [])[:24]
                if hourly_meta.get("stale_cache"):
                    warnings.append("Using stale cached NWS hourly forecast because the live request failed.")

            raw = {
                "point": point_payload,
                "latest_station": latest_station,
                "latest_observation": latest_observation,
                "forecast_periods": forecast_periods,
                "hourly_periods": hourly_periods,
                "point_cache_hit": point_meta.get("cache_hit", False),
            }
            return self.normalize_response(raw, latitude=latitude, longitude=longitude, warnings=warnings)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"NWS request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        warnings = list(kwargs.get("warnings", []))
        observation = raw.get("latest_observation", {}) or {}
        station = (raw.get("latest_station", {}) or {}).get("properties", {}) or {}
        daily_rows = []
        for item in raw.get("forecast_periods", []):
            daily_rows.append(
                {
                    "name": item.get("name"),
                    "start_time": item.get("startTime"),
                    "temperature_f": item.get("temperature"),
                    "temperature_unit": item.get("temperatureUnit"),
                    "wind_speed_mph": parse_wind_speed_text(item.get("windSpeed")),
                    "wind_direction": item.get("windDirection"),
                    "probability_of_precipitation_pct": (item.get("probabilityOfPrecipitation") or {}).get("value"),
                    "summary": item.get("shortForecast"),
                }
            )

        hourly_rows = []
        for item in raw.get("hourly_periods", []):
            hourly_rows.append(
                {
                    "time": item.get("startTime"),
                    "temperature_f": item.get("temperature"),
                    "wind_speed_mph": parse_wind_speed_text(item.get("windSpeed")),
                    "wind_direction": item.get("windDirection"),
                    "probability_of_precipitation_pct": (item.get("probabilityOfPrecipitation") or {}).get("value"),
                    "summary": item.get("shortForecast"),
                }
            )

        current = {
            "station_id": station.get("stationIdentifier") or station.get("stationName"),
            "station_name": station.get("name"),
            "observation_time": observation.get("timestamp"),
            "temperature_f": _convert_value(observation.get("temperature"), "temperature"),
            "humidity_pct": _convert_value(observation.get("relativeHumidity"), "humidity"),
            "wind_speed_mph": _convert_value(observation.get("windSpeed"), "wind"),
            "wind_gust_mph": _convert_value(observation.get("windGust"), "wind"),
            "wind_direction_deg": _convert_value(observation.get("windDirection"), "direction"),
            "barometric_pressure_pa": _convert_value(observation.get("barometricPressure"), "pressure"),
            "precipitation_last_hour_in": _convert_value(observation.get("precipitationLastHour"), "precipitation"),
            "text_description": observation.get("textDescription"),
        }

        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={
                "current": current,
                "daily": daily_rows,
                "hourly_preview": hourly_rows,
            },
            units={
                "temperature": "F",
                "wind_speed": "mph",
                "precipitation": "in",
                "humidity": "%",
            },
            raw_metadata={
                "forecast_office": ((raw.get("point", {}) or {}).get("properties", {}) or {}).get("gridId"),
                "cache_hit": raw.get("point_cache_hit", False),
            },
            warnings=warnings,
        )
