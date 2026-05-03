from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd
import requests


WMO_WEATHER_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Dense Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    80: "Rain Showers",
    81: "Heavy Showers",
    82: "Violent Showers",
    95: "Thunderstorm",
    96: "Storm Hail",
    99: "Severe Storm Hail",
}


def build_week_index(weeks: int, end_date: str | pd.Timestamp | None = None) -> pd.DatetimeIndex:
    """Return weekly Monday anchors for the requested history window."""
    anchor = pd.Timestamp(end_date or pd.Timestamp.today()).normalize()
    week_start = anchor - pd.to_timedelta(anchor.weekday(), unit="D")
    return pd.date_range(end=week_start, periods=weeks, freq="W-MON")


def generate_synthetic_weather(
    pastures: pd.DataFrame,
    week_starts: pd.DatetimeIndex,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic weekly weather shaped for a semi-arid central Texas ranch."""
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []

    for pasture_idx, pasture in pastures.reset_index(drop=True).iterrows():
        pasture_bias = rng.normal(0, 2.2)
        for week_index, week_start in enumerate(week_starts):
            week_of_year = int(pd.Timestamp(week_start).isocalendar().week)
            rainfall_season = 14 + 8 * np.sin(((week_of_year - 8) / 52) * 2 * np.pi)
            temperature_season = 23 + 11 * np.sin(((week_of_year - 15) / 52) * 2 * np.pi)
            drought_cycle = 3 * np.sin(((week_index + pasture_idx) / 11) * 2 * np.pi)

            rainfall_7d = max(
                0.0,
                rainfall_season + pasture_bias - drought_cycle + rng.gamma(shape=2.1, scale=3.6) - 5,
            )
            temp_avg_7d = temperature_season + rng.normal(0, 1.8) + pasture_idx * 0.35
            temp_max_7d = temp_avg_7d + rng.uniform(5.5, 11.5)

            records.append(
                {
                    "pasture_id": pasture["pasture_id"],
                    "week_start": pd.Timestamp(week_start),
                    "rainfall_7d": round(rainfall_7d, 2),
                    "temp_avg_7d": round(temp_avg_7d, 2),
                    "temp_max_7d": round(temp_max_7d, 2),
                }
            )

    return pd.DataFrame(records).sort_values(["pasture_id", "week_start"]).reset_index(drop=True)


def weather_code_label(code: int | str | None) -> str:
    if code is None or (isinstance(code, float) and np.isnan(code)):
        return "Unknown"
    try:
        return WMO_WEATHER_CODES.get(int(code), str(code))
    except (TypeError, ValueError):
        return str(code)


def cardinal_direction(degrees: float | None) -> str | None:
    if degrees is None or pd.isna(degrees):
        return None
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = round(float(degrees) / 45) % 8
    return directions[idx]


def celsius_to_fahrenheit(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) * 9 / 5 + 32


def kmh_to_mph(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) * 0.621371


def ms_to_mph(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) * 2.23694


def mm_to_inches(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) / 25.4


def parse_wind_speed_text(text: str | None) -> float | None:
    if not text:
        return None
    parts = [part for part in text.replace("mph", "").replace("MPH", "").replace("to", " ").split() if part.replace(".", "", 1).isdigit()]
    if not parts:
        return None
    values = [float(part) for part in parts]
    return round(sum(values) / len(values), 1)


def _convert_quantitative_value(item: dict[str, Any] | None, kind: str) -> float | None:
    if not item:
        return None
    value = item.get("value")
    unit = item.get("unitCode", "")
    if value is None:
        return None

    if kind == "temp_f":
        if "degC" in unit:
            return celsius_to_fahrenheit(value)
        return float(value)
    if kind == "wind_mph":
        if "km_h" in unit or "km/h" in unit:
            return kmh_to_mph(value)
        if "m_s" in unit or "m/s" in unit:
            return ms_to_mph(value)
        return float(value)
    if kind == "precip_in":
        if "mm" in unit:
            return mm_to_inches(value)
        if "m" in unit:
            return float(value) * 39.3701
        return float(value)
    if kind == "pct":
        return float(value)
    if kind == "deg":
        return float(value)
    return float(value)


class WeatherProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def get_current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_7day_forecast(self, lat: float, lon: float) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_hourly_forecast(self, lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
        raise NotImplementedError


class MockWeatherProvider(WeatherProvider):
    provider_name = "mock"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _hourly_base(self, lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
        current_time = pd.Timestamp.now().floor("h")
        rng_seed = int(abs(lat * 1000) + abs(lon * 1000) + self.seed)
        rng = np.random.default_rng(rng_seed)
        index = pd.date_range(start=current_time, periods=hours, freq="h")
        rows: list[dict[str, object]] = []

        for step_idx, timestamp in enumerate(index):
            day_fraction = np.sin(((timestamp.hour - 5) / 24) * 2 * np.pi)
            temperature_f = 79 + day_fraction * 14 + rng.normal(0, 2)
            wind_speed_mph = np.clip(9 + rng.normal(0, 3) + abs(day_fraction) * 7, 2, 32)
            wind_gust_mph = wind_speed_mph + rng.uniform(3, 12)
            humidity_pct = np.clip(44 - day_fraction * 12 - (temperature_f - 82) * 0.4 + rng.normal(0, 4), 12, 94)
            precip_probability = np.clip(18 + rng.normal(0, 12) + max(0, -day_fraction * 15), 0, 88)
            precip_in = max(0.0, rng.gamma(1.3, 0.03) if precip_probability > 45 and rng.random() < 0.3 else 0.0)
            weather_code = 63 if precip_in > 0.15 else 61 if precip_in > 0.02 else 3 if humidity_pct > 55 else 1
            feels_like_f = temperature_f + max(0, (temperature_f - 82) * 0.2) - max(0, wind_speed_mph - 15) * 0.15
            wind_dir_deg = (step_idx * 15 + rng.normal(180, 35)) % 360

            rows.append(
                {
                    "timestamp": timestamp,
                    "temperature_f": round(float(temperature_f), 1),
                    "feels_like_f": round(float(feels_like_f), 1),
                    "humidity_pct": round(float(humidity_pct), 1),
                    "wind_speed_mph": round(float(wind_speed_mph), 1),
                    "wind_gust_mph": round(float(wind_gust_mph), 1),
                    "wind_direction_deg": round(float(wind_dir_deg), 1),
                    "wind_direction": cardinal_direction(float(wind_dir_deg)),
                    "precip_probability_pct": round(float(precip_probability), 1),
                    "expected_precip_in": round(float(precip_in), 3),
                    "weather_code": weather_code,
                    "weather_label": weather_code_label(weather_code),
                }
            )

        return pd.DataFrame(rows)

    def get_current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        hourly = self._hourly_base(lat, lon, hours=24)
        current = hourly.iloc[0].to_dict()
        today_rain = hourly.loc[hourly["timestamp"].dt.date == hourly["timestamp"].iloc[0].date(), "expected_precip_in"].sum()
        current["rainfall_expected_today_in"] = round(float(today_rain), 3)
        current["source"] = "MockWeatherProvider"
        current["observation_time"] = current["timestamp"]
        return current

    def get_7day_forecast(self, lat: float, lon: float) -> pd.DataFrame:
        hourly = self._hourly_base(lat, lon, hours=24 * 7)
        hourly["date"] = hourly["timestamp"].dt.date
        daily = (
            hourly.groupby("date", as_index=False)
            .agg(
                high_temp_f=("temperature_f", "max"),
                low_temp_f=("temperature_f", "min"),
                precip_probability_pct=("precip_probability_pct", "max"),
                expected_precip_in=("expected_precip_in", "sum"),
                wind_speed_mph=("wind_speed_mph", "mean"),
                wind_gust_mph=("wind_gust_mph", "max"),
                weather_code=("weather_code", lambda series: series.mode().iloc[0]),
            )
            .round(2)
        )
        daily["weather_label"] = daily["weather_code"].apply(weather_code_label)
        return daily.head(7)

    def get_hourly_forecast(self, lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
        return self._hourly_base(lat, lon, hours=hours)


class OpenMeteoWeatherProvider(WeatherProvider):
    provider_name = "openmeteo"

    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    def _fetch(self, lat: float, lon: float) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "precipitation_probability",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "wind_direction_10m",
                ]
            ),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "precipitation_probability",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "wind_direction_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "precipitation_sum",
                    "wind_speed_10m_max",
                    "wind_gusts_10m_max",
                    "wind_direction_10m_dominant",
                ]
            ),
            "forecast_days": 7,
        }
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def get_current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        payload = self._fetch(lat, lon)
        current = payload.get("current", {})
        hourly = payload.get("hourly", {})
        times = pd.to_datetime(hourly.get("time", []))
        precip = pd.Series(hourly.get("precipitation", []), dtype="float64")
        today_mask = times.date == pd.Timestamp.now().date() if len(times) else []
        today_rain = float(precip.loc[today_mask].sum()) if len(times) else 0.0
        wind_dir_deg = current.get("wind_direction_10m")

        return {
            "observation_time": pd.to_datetime(current.get("time")) if current.get("time") else pd.Timestamp.now(),
            "temperature_f": current.get("temperature_2m"),
            "feels_like_f": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_mph": current.get("wind_speed_10m"),
            "wind_gust_mph": current.get("wind_gusts_10m"),
            "wind_direction_deg": wind_dir_deg,
            "wind_direction": cardinal_direction(wind_dir_deg),
            "precip_probability_pct": current.get("precipitation_probability"),
            "rainfall_expected_today_in": round(today_rain, 3),
            "weather_code": current.get("weather_code"),
            "weather_label": weather_code_label(current.get("weather_code")),
            "source": "Open-Meteo Forecast API",
        }

    def get_7day_forecast(self, lat: float, lon: float) -> pd.DataFrame:
        payload = self._fetch(lat, lon)
        daily = payload.get("daily", {})
        forecast = pd.DataFrame(
            {
                "date": pd.to_datetime(daily.get("time", [])).date,
                "high_temp_f": daily.get("temperature_2m_max", []),
                "low_temp_f": daily.get("temperature_2m_min", []),
                "precip_probability_pct": daily.get("precipitation_probability_max", []),
                "expected_precip_in": daily.get("precipitation_sum", []),
                "wind_speed_mph": daily.get("wind_speed_10m_max", []),
                "wind_gust_mph": daily.get("wind_gusts_10m_max", []),
                "wind_direction_deg": daily.get("wind_direction_10m_dominant", []),
                "weather_code": daily.get("weather_code", []),
            }
        )
        forecast["weather_label"] = forecast["weather_code"].apply(weather_code_label)
        forecast["wind_direction"] = forecast["wind_direction_deg"].apply(cardinal_direction)
        return forecast.head(7)

    def get_hourly_forecast(self, lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
        payload = self._fetch(lat, lon)
        hourly = payload.get("hourly", {})
        forecast = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(hourly.get("time", [])),
                "temperature_f": hourly.get("temperature_2m", []),
                "feels_like_f": hourly.get("apparent_temperature", []),
                "humidity_pct": hourly.get("relative_humidity_2m", []),
                "wind_speed_mph": hourly.get("wind_speed_10m", []),
                "wind_gust_mph": hourly.get("wind_gusts_10m", []),
                "wind_direction_deg": hourly.get("wind_direction_10m", []),
                "precip_probability_pct": hourly.get("precipitation_probability", []),
                "expected_precip_in": hourly.get("precipitation", []),
                "weather_code": hourly.get("weather_code", []),
            }
        )
        forecast["wind_direction"] = forecast["wind_direction_deg"].apply(cardinal_direction)
        forecast["weather_label"] = forecast["weather_code"].apply(weather_code_label)
        return forecast.head(hours)


class NWSWeatherProvider(WeatherProvider):
    provider_name = "nws"

    def __init__(self, user_agent: str, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/geo+json"})

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def _points(self, lat: float, lon: float) -> dict[str, Any]:
        return self._get_json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")

    def _hourly_periods(self, lat: float, lon: float) -> list[dict[str, Any]]:
        points_payload = self._points(lat, lon)
        hourly_url = points_payload["properties"]["forecastHourly"]
        return self._get_json(hourly_url)["properties"]["periods"]

    def get_hourly_forecast(self, lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
        periods = self._hourly_periods(lat, lon)[:hours]
        rows: list[dict[str, Any]] = []
        for period in periods:
            wind_speed = parse_wind_speed_text(period.get("windSpeed"))
            wind_direction = period.get("windDirection")
            precip_prob = period.get("probabilityOfPrecipitation", {}).get("value")
            rows.append(
                {
                    "timestamp": pd.to_datetime(period.get("startTime")),
                    "temperature_f": period.get("temperature"),
                    "feels_like_f": period.get("temperature"),
                    "humidity_pct": None,
                    "wind_speed_mph": wind_speed,
                    "wind_gust_mph": None,
                    "wind_direction_deg": None,
                    "wind_direction": wind_direction,
                    "precip_probability_pct": precip_prob,
                    "expected_precip_in": None,
                    "weather_code": None,
                    "weather_label": period.get("shortForecast"),
                }
            )
        return pd.DataFrame(rows)

    def get_7day_forecast(self, lat: float, lon: float) -> pd.DataFrame:
        hourly = self.get_hourly_forecast(lat, lon, hours=24 * 7)
        hourly["date"] = pd.to_datetime(hourly["timestamp"]).dt.date
        grouped = (
            hourly.groupby("date", as_index=False)
            .agg(
                high_temp_f=("temperature_f", "max"),
                low_temp_f=("temperature_f", "min"),
                precip_probability_pct=("precip_probability_pct", "max"),
                wind_speed_mph=("wind_speed_mph", "mean"),
                weather_label=("weather_label", lambda series: series.dropna().iloc[0] if not series.dropna().empty else "Forecast"),
            )
            .round(2)
        )
        grouped["expected_precip_in"] = None
        grouped["wind_gust_mph"] = None
        grouped["weather_code"] = None
        return grouped.head(7)

    def get_current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        points_payload = self._points(lat, lon)
        stations_url = points_payload["properties"]["observationStations"]
        stations_payload = self._get_json(stations_url)
        station_features = stations_payload.get("features", [])
        if not station_features:
            raise ValueError("No NWS observation stations were returned for this location.")

        station_id = station_features[0].get("properties", {}).get("stationIdentifier")
        if not station_id:
            identifier = station_features[0].get("id", "")
            station_id = identifier.rsplit("/", 1)[-1]

        observation = self._get_json(f"https://api.weather.gov/stations/{station_id}/observations/latest")
        properties = observation.get("properties", {})
        hourly = self.get_hourly_forecast(lat, lon, hours=24)
        today_mask = pd.to_datetime(hourly["timestamp"]).dt.date == pd.Timestamp.now().date()
        rain_today = hourly.loc[today_mask, "expected_precip_in"].dropna().sum() if "expected_precip_in" in hourly else None
        wind_dir_deg = _convert_quantitative_value(properties.get("windDirection"), "deg")
        temp_f = _convert_quantitative_value(properties.get("temperature"), "temp_f")
        feels_like_f = _convert_quantitative_value(properties.get("heatIndex"), "temp_f") or _convert_quantitative_value(
            properties.get("windChill"), "temp_f"
        ) or temp_f

        return {
            "observation_time": pd.to_datetime(properties.get("timestamp")) if properties.get("timestamp") else pd.Timestamp.now(),
            "temperature_f": round(temp_f, 1) if temp_f is not None else None,
            "feels_like_f": round(feels_like_f, 1) if feels_like_f is not None else None,
            "humidity_pct": _convert_quantitative_value(properties.get("relativeHumidity"), "pct"),
            "wind_speed_mph": round(_convert_quantitative_value(properties.get("windSpeed"), "wind_mph"), 1)
            if _convert_quantitative_value(properties.get("windSpeed"), "wind_mph") is not None
            else None,
            "wind_gust_mph": round(_convert_quantitative_value(properties.get("windGust"), "wind_mph"), 1)
            if _convert_quantitative_value(properties.get("windGust"), "wind_mph") is not None
            else None,
            "wind_direction_deg": wind_dir_deg,
            "wind_direction": cardinal_direction(wind_dir_deg),
            "precip_probability_pct": hourly["precip_probability_pct"].iloc[0] if not hourly.empty else None,
            "rainfall_expected_today_in": round(float(rain_today), 3) if rain_today is not None else None,
            "weather_code": None,
            "weather_label": properties.get("textDescription") or "Current conditions",
            "source": f"NWS {station_id}",
        }
