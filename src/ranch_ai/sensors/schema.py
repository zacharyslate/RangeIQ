from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


SUPPORTED_STATION_TYPES = (
    "weather",
    "soil",
    "water_tank",
    "trough",
    "relay",
    "combined",
    "experimental",
)

STATION_STATUS_VALUES = ("ONLINE", "STALE", "OFFLINE")

SENSOR_READING_FIELDS = [
    "station_id",
    "pasture_id",
    "timestamp",
    "air_temp_f",
    "humidity_pct",
    "pressure_hpa",
    "rainfall_in",
    "soil_moisture_10cm",
    "soil_moisture_30cm",
    "soil_moisture_60cm",
    "soil_temp_f",
    "water_tank_pct",
    "trough_level_pct",
    "battery_voltage",
    "solar_voltage",
    "signal_strength",
    "rssi",
    "snr",
    "hop_count",
    "firmware_version",
    "notes",
]


@dataclass
class SensorReading:
    station_id: str
    pasture_id: str
    timestamp: pd.Timestamp
    air_temp_f: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    rainfall_in: float | None = None
    soil_moisture_10cm: float | None = None
    soil_moisture_30cm: float | None = None
    soil_moisture_60cm: float | None = None
    soil_temp_f: float | None = None
    water_tank_pct: float | None = None
    trough_level_pct: float | None = None
    battery_voltage: float | None = None
    solar_voltage: float | None = None
    signal_strength: float | None = None
    rssi: float | None = None
    snr: float | None = None
    hop_count: int | None = None
    firmware_version: str = ""
    notes: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = pd.Timestamp(self.timestamp)
        return record


@dataclass
class SensorStation:
    station_id: str
    station_name: str
    pasture_id: str
    station_type: str
    latitude: float
    longitude: float
    installed_at: pd.Timestamp
    expected_interval_minutes: int
    sensors: list[str] = field(default_factory=list)
    active: bool = True
    notes: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["installed_at"] = pd.Timestamp(self.installed_at)
        record["sensors"] = ",".join(self.sensors)
        return record


@dataclass
class StationStatus:
    station_id: str
    last_seen: pd.Timestamp | None
    status: str
    battery_status: str
    signal_status: str
    sensor_error_status: str
    alerts: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["last_seen"] = pd.Timestamp(self.last_seen) if self.last_seen is not None else pd.NaT
        record["alerts"] = list(self.alerts)
        return record
