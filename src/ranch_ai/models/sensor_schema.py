from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SensorStatus:
    station_id: str
    pasture_id: str
    station_name: str
    last_contact: pd.Timestamp
    status: str
    data_freshness_minutes: float
    battery_voltage: float | None
    signal_strength: float | None
    low_battery: bool
    low_signal: bool
    sensor_error: bool
    water_tank_pct: float | None
    trough_level_pct: float | None
    camera_status: str


@dataclass
class SensorBundle:
    readings: pd.DataFrame
    latest_status: pd.DataFrame
    alerts: pd.DataFrame
    provider_name: str
    mode: str
    source_message: str
    loaded_at: pd.Timestamp
