from __future__ import annotations

from typing import Any

from ranch_ai.data_sources.base import BaseDataSourceProvider


class OpenMeteoDataSource(BaseDataSourceProvider):
    name = "open_meteo"
    category = "weather"
    requires_key = False
    access_level = "no_key_free_noncommercial"
    commercial_safe = False
    citation_url = "https://open-meteo.com/en/pricing"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "Open-Meteo is disabled in config/api_sources.yaml.")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": kwargs.get("timezone", "auto"),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "precipitation_probability",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "wind_direction_10m",
                    "soil_moisture_0_to_1cm",
                    "soil_temperature_0cm",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "wind_gusts_10m_max",
                ]
            ),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation_probability",
                    "precipitation",
                    "wind_speed_10m",
                    "soil_moisture_0_to_1cm",
                    "soil_temperature_0cm",
                    "evapotranspiration",
                ]
            ),
            "forecast_days": int(kwargs.get("forecast_days", 7)),
        }
        try:
            raw, request_meta = self._request_json(
                url=self.config.get("endpoint_url", "https://api.open-meteo.com/v1/forecast"),
                params=params,
                cache_context={"kind": "point", "latitude": round(latitude, 5), "longitude": round(longitude, 5)},
            )
            return self.normalize_response(raw, latitude=latitude, longitude=longitude, request_meta=request_meta)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"Open-Meteo request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        request_meta = kwargs.get("request_meta", {})
        current_payload = raw.get("current", {})
        daily_payload = raw.get("daily", {})
        hourly_payload = raw.get("hourly", {})
        warnings: list[str] = []
        default_warning = self._default_warning()
        if default_warning:
            warnings.append(default_warning)
        if request_meta.get("stale_cache"):
            warnings.append("Using stale cached Open-Meteo response because the live request failed.")

        daily_rows = []
        dates = daily_payload.get("time", []) or []
        for index, date_value in enumerate(dates):
            daily_rows.append(
                {
                    "date": date_value,
                    "weather_code": (daily_payload.get("weather_code", []) or [None])[index],
                    "temperature_max_f": (daily_payload.get("temperature_2m_max", []) or [None])[index],
                    "temperature_min_f": (daily_payload.get("temperature_2m_min", []) or [None])[index],
                    "precipitation_probability_pct": (daily_payload.get("precipitation_probability_max", []) or [None])[index],
                    "precipitation_in": (daily_payload.get("precipitation_sum", []) or [None])[index],
                    "wind_speed_mph": (daily_payload.get("wind_speed_10m_max", []) or [None])[index],
                    "wind_gust_mph": (daily_payload.get("wind_gusts_10m_max", []) or [None])[index],
                }
            )

        hourly_rows = []
        hours = hourly_payload.get("time", []) or []
        for index, hour in enumerate(hours[:24]):
            hourly_rows.append(
                {
                    "time": hour,
                    "temperature_f": (hourly_payload.get("temperature_2m", []) or [None])[index],
                    "humidity_pct": (hourly_payload.get("relative_humidity_2m", []) or [None])[index],
                    "precipitation_probability_pct": (hourly_payload.get("precipitation_probability", []) or [None])[index],
                    "precipitation_in": (hourly_payload.get("precipitation", []) or [None])[index],
                    "wind_speed_mph": (hourly_payload.get("wind_speed_10m", []) or [None])[index],
                    "soil_moisture_0_to_1cm": (hourly_payload.get("soil_moisture_0_to_1cm", []) or [None])[index],
                    "soil_temperature_0cm_f": (hourly_payload.get("soil_temperature_0cm", []) or [None])[index],
                    "evapotranspiration_in": (hourly_payload.get("evapotranspiration", []) or [None])[index],
                }
            )

        data = {
            "current": {
                "time": current_payload.get("time"),
                "temperature_f": current_payload.get("temperature_2m"),
                "feels_like_f": current_payload.get("apparent_temperature"),
                "humidity_pct": current_payload.get("relative_humidity_2m"),
                "precipitation_in": current_payload.get("precipitation"),
                "precipitation_probability_pct": current_payload.get("precipitation_probability"),
                "wind_speed_mph": current_payload.get("wind_speed_10m"),
                "wind_gust_mph": current_payload.get("wind_gusts_10m"),
                "wind_direction_deg": current_payload.get("wind_direction_10m"),
                "soil_moisture_0_to_1cm": current_payload.get("soil_moisture_0_to_1cm"),
                "soil_temperature_0cm_f": current_payload.get("soil_temperature_0cm"),
            },
            "daily": daily_rows,
            "hourly_preview": hourly_rows,
        }
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data=data,
            units={
                "temperature": "F",
                "wind_speed": "mph",
                "precipitation": "in",
                "humidity": "%",
                "soil_moisture": "m3/m3",
            },
            raw_metadata={
                "cache_hit": request_meta.get("cache_hit", False),
                "timezone": raw.get("timezone"),
                "generationtime_ms": raw.get("generationtime_ms"),
            },
            warnings=warnings,
        )
