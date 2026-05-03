from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from ranch_ai.sensors.schema import SENSOR_READING_FIELDS, SensorReading, SensorStation


MOCK_STATION_BLUEPRINTS = [
    {
        "station_id": "NP1",
        "station_name": "North Pasture Soil Station",
        "station_type": "soil",
        "lat_offset": 0.0017,
        "lon_offset": -0.0014,
        "sensors": ["air_temp_f", "humidity_pct", "soil_moisture_10cm", "soil_moisture_30cm", "soil_moisture_60cm", "soil_temp_f", "battery_voltage", "solar_voltage", "rssi", "snr"],
    },
    {
        "station_id": "SP1",
        "station_name": "South Pasture Soil Station",
        "station_type": "soil",
        "lat_offset": -0.0012,
        "lon_offset": 0.0014,
        "sensors": ["air_temp_f", "humidity_pct", "soil_moisture_10cm", "soil_moisture_30cm", "soil_moisture_60cm", "soil_temp_f", "battery_voltage", "solar_voltage", "rssi", "snr"],
    },
    {
        "station_id": "WT1",
        "station_name": "Main Stock Tank",
        "station_type": "water_tank",
        "lat_offset": 0.0006,
        "lon_offset": 0.0005,
        "sensors": ["water_tank_pct", "trough_level_pct", "battery_voltage", "solar_voltage", "rssi", "snr"],
    },
    {
        "station_id": "WX1",
        "station_name": "Ranch Weather Station",
        "station_type": "weather",
        "lat_offset": 0.0011,
        "lon_offset": 0.0018,
        "sensors": ["air_temp_f", "humidity_pct", "pressure_hpa", "rainfall_in", "battery_voltage", "solar_voltage", "rssi", "snr"],
    },
    {
        "station_id": "RLY1",
        "station_name": "Hilltop Relay",
        "station_type": "relay",
        "lat_offset": 0.0029,
        "lon_offset": 0.0002,
        "sensors": ["battery_voltage", "solar_voltage", "rssi", "snr", "hop_count"],
    },
]


def build_mock_station_registry(
    base_lat: float,
    base_lon: float,
    pasture_id: str = "CC-001",
    expected_interval_minutes: int = 60,
) -> list[SensorStation]:
    installed_at = pd.Timestamp("2026-03-15 08:00:00")
    stations: list[SensorStation] = []
    for blueprint in MOCK_STATION_BLUEPRINTS:
        stations.append(
            SensorStation(
                station_id=blueprint["station_id"],
                station_name=blueprint["station_name"],
                pasture_id=pasture_id,
                station_type=blueprint["station_type"],
                latitude=base_lat + blueprint["lat_offset"],
                longitude=base_lon + blueprint["lon_offset"],
                installed_at=installed_at,
                expected_interval_minutes=expected_interval_minutes,
                sensors=list(blueprint["sensors"]),
                active=True,
                notes="Mock RangeIQ sensor-network starter station.",
            )
        )
    return stations


def sensor_readings_to_dataframe(readings: list[SensorReading]) -> pd.DataFrame:
    rows = []
    for reading in readings:
        record = asdict(reading)
        record["timestamp"] = pd.Timestamp(reading.timestamp)
        rows.append(record)
    if not rows:
        return pd.DataFrame(columns=SENSOR_READING_FIELDS)
    df = pd.DataFrame(rows)
    for column in SENSOR_READING_FIELDS:
        if column not in df.columns:
            df[column] = np.nan
    return df[SENSOR_READING_FIELDS].sort_values(["station_id", "timestamp"]).reset_index(drop=True)


def generate_mock_sensor_readings(
    stations: list[SensorStation],
    seed: int = 42,
    days: int = 7,
    end_time: pd.Timestamp | None = None,
) -> list[SensorReading]:
    rng = np.random.default_rng(seed + 915)
    end_timestamp = (end_time or pd.Timestamp.now()).floor("h")
    hourly_index = pd.date_range(end=end_timestamp, periods=days * 24, freq="h")
    readings: list[SensorReading] = []

    for station in stations:
        effective_index = hourly_index
        if station.station_id == "SP1":
            effective_index = hourly_index[:-16]

        for step, timestamp in enumerate(effective_index):
            diurnal = np.sin(((timestamp.hour - 5) / 24) * 2 * np.pi)
            air_temp = 83 + diurnal * 16 + rng.normal(0, 2.1)
            humidity = np.clip(37 - diurnal * 12 + rng.normal(0, 5.4), 9, 98)
            pressure = 1008 + rng.normal(0, 3.0)
            rainfall = 0.0 if rng.random() > 0.08 else round(float(rng.gamma(1.5, 0.04)), 3)
            battery = 4.03 - step * 0.0005 + rng.normal(0, 0.015)
            solar = 5.35 + max(diurnal, 0) * 0.9 + rng.normal(0, 0.05)
            rssi = float(np.clip(-93 + rng.normal(0, 4), -126, -78))
            snr = round(float(np.clip(8 + rng.normal(0, 2.5), -9, 14)), 2)
            hop_count = 1 if station.station_id != "RLY1" else 0

            soil_10 = np.clip(18 + diurnal * 1.5 + rng.normal(0, 1.4), 5, 40)
            soil_30 = np.clip(20 + diurnal * 1.2 + rng.normal(0, 1.1), 6, 42)
            soil_60 = np.clip(23 + diurnal * 0.9 + rng.normal(0, 0.9), 8, 45)
            water_tank = np.nan
            trough_level = np.nan
            notes = ""

            if station.station_id == "NP1":
                soil_10 = np.clip(13.2 + diurnal * 0.9 + rng.normal(0, 1.0) - step * 0.004, 4, 24)
                soil_30 = np.clip(18.5 + diurnal * 0.6 + rng.normal(0, 0.8) - step * 0.003, 8, 28)
                soil_60 = np.clip(21.0 + diurnal * 0.4 + rng.normal(0, 0.7) - step * 0.002, 10, 32)
                notes = "Dry ridge profile."
            elif station.station_id == "SP1":
                rssi = float(np.clip(-109 + rng.normal(0, 3), -124, -96))
                notes = "Station is overdue and used for stale/offline testing."
            elif station.station_id == "WT1":
                battery = 3.44 - step * 0.0009 + rng.normal(0, 0.01)
                water_tank = np.clip(31 - step * 0.11 + rng.normal(0, 1.1), 11, 40)
                trough_level = np.clip(water_tank - 6 + rng.normal(0, 2.0), 5, 34)
                notes = "Low tank and battery warning example."
            elif station.station_id == "WX1":
                soil_10 = soil_30 = soil_60 = np.nan
                water_tank = trough_level = np.nan
                notes = "Primary weather station."
            elif station.station_id == "RLY1":
                air_temp = humidity = pressure = rainfall = soil_10 = soil_30 = soil_60 = np.nan
                water_tank = trough_level = np.nan
                battery = 3.83 - step * 0.0003 + rng.normal(0, 0.02)
                solar = 5.55 + max(diurnal, 0) * 1.1 + rng.normal(0, 0.08)
                rssi = float(np.clip(-118 + rng.normal(0, 2.5), -126, -108))
                snr = round(float(np.clip(2 + rng.normal(0, 1.2), -6, 5)), 2)
                hop_count = 0
                notes = "Hilltop relay node with marginal signal."

            readings.append(
                SensorReading(
                    station_id=station.station_id,
                    pasture_id=station.pasture_id,
                    timestamp=pd.Timestamp(timestamp),
                    air_temp_f=None if pd.isna(air_temp) else round(float(air_temp), 2),
                    humidity_pct=None if pd.isna(humidity) else round(float(humidity), 2),
                    pressure_hpa=None if pd.isna(pressure) else round(float(pressure), 2),
                    rainfall_in=None if pd.isna(rainfall) else round(float(rainfall), 3),
                    soil_moisture_10cm=None if pd.isna(soil_10) else round(float(soil_10), 2),
                    soil_moisture_30cm=None if pd.isna(soil_30) else round(float(soil_30), 2),
                    soil_moisture_60cm=None if pd.isna(soil_60) else round(float(soil_60), 2),
                    soil_temp_f=None if pd.isna(air_temp) else round(float(air_temp * 0.92 + rng.normal(0, 1.3)), 2),
                    water_tank_pct=None if pd.isna(water_tank) else round(float(water_tank), 2),
                    trough_level_pct=None if pd.isna(trough_level) else round(float(trough_level), 2),
                    battery_voltage=round(float(np.clip(battery, 3.1, 4.25)), 2),
                    solar_voltage=round(float(np.clip(solar, 0.0, 7.0)), 2),
                    signal_strength=round(float(rssi), 1),
                    rssi=round(float(rssi), 1),
                    snr=float(snr),
                    hop_count=hop_count,
                    firmware_version="rangeiq-mock-0.1",
                    notes=notes,
                )
            )

    return readings
