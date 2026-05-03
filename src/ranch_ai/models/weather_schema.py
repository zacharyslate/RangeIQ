from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class WeatherCurrent:
    observation_time: pd.Timestamp
    temperature_f: float | None
    feels_like_f: float | None
    humidity_pct: float | None
    wind_speed_mph: float | None
    wind_gust_mph: float | None
    wind_direction_deg: float | None
    wind_direction: str | None
    precip_probability_pct: float | None
    rainfall_expected_today_in: float | None
    weather_code: int | str | None
    weather_label: str
    source: str


@dataclass
class WeatherBundle:
    current: WeatherCurrent
    forecast: pd.DataFrame
    hourly: pd.DataFrame
    provider_name: str
    mode: str
    source_message: str
    loaded_at: pd.Timestamp
