from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ranch_ai.sensors.schema import SensorReading, SensorStation, StationStatus
from ranch_ai.sensors.validation import validate_sensor_reading


@dataclass
class SensorStatusThresholds:
    expected_interval_minutes: int = 60
    stale_after_minutes: int = 180
    offline_after_minutes: int = 720
    low_battery_voltage: float = 3.5
    low_signal_rssi: float = -115
    low_water_tank_pct: float = 25


def classify_connection_status(last_seen: pd.Timestamp | None, now: pd.Timestamp, thresholds: SensorStatusThresholds) -> str:
    if last_seen is None or pd.isna(last_seen):
        return "OFFLINE"
    age_minutes = (now - pd.Timestamp(last_seen)).total_seconds() / 60
    if age_minutes >= thresholds.offline_after_minutes:
        return "OFFLINE"
    if age_minutes >= thresholds.stale_after_minutes:
        return "STALE"
    return "ONLINE"


def classify_battery_status(battery_voltage: float | None, thresholds: SensorStatusThresholds) -> str:
    if battery_voltage is None or pd.isna(battery_voltage):
        return "UNKNOWN"
    return "LOW_BATTERY" if float(battery_voltage) < thresholds.low_battery_voltage else "OK"


def classify_signal_status(rssi: float | None, thresholds: SensorStatusThresholds) -> str:
    if rssi is None or pd.isna(rssi):
        return "UNKNOWN"
    return "LOW_SIGNAL" if float(rssi) < thresholds.low_signal_rssi else "OK"


def classify_sensor_error(reading: SensorReading) -> str:
    return "SENSOR_ERROR" if validate_sensor_reading(reading) else "OK"


def classify_station_status(
    station: SensorStation,
    reading: SensorReading | None,
    now: pd.Timestamp,
    thresholds: SensorStatusThresholds,
) -> StationStatus:
    if reading is None:
        return StationStatus(
            station_id=station.station_id,
            last_seen=None,
            status="OFFLINE",
            battery_status="UNKNOWN",
            signal_status="UNKNOWN",
            sensor_error_status="UNKNOWN",
            alerts=["OFFLINE"],
        )

    status = classify_connection_status(reading.timestamp, now, thresholds)
    battery_status = classify_battery_status(reading.battery_voltage, thresholds)
    signal_status = classify_signal_status(reading.rssi if reading.rssi is not None else reading.signal_strength, thresholds)
    sensor_error_status = classify_sensor_error(reading)
    alerts = [flag for flag in [status if status != "ONLINE" else "", battery_status if battery_status != "OK" else "", signal_status if signal_status != "OK" else "", sensor_error_status if sensor_error_status != "OK" else ""] if flag]
    if reading.water_tank_pct is not None and reading.water_tank_pct < thresholds.low_water_tank_pct:
        alerts.append("LOW_WATER_TANK")

    return StationStatus(
        station_id=station.station_id,
        last_seen=pd.Timestamp(reading.timestamp),
        status=status,
        battery_status=battery_status,
        signal_status=signal_status,
        sensor_error_status=sensor_error_status,
        alerts=alerts,
    )


def build_station_status_table(
    stations: list[SensorStation],
    readings_df: pd.DataFrame,
    now: pd.Timestamp,
    thresholds: SensorStatusThresholds,
) -> list[StationStatus]:
    latest_lookup: dict[str, SensorReading] = {}
    if not readings_df.empty:
        latest_df = readings_df.sort_values("timestamp").groupby("station_id", as_index=False).tail(1)
        for row in latest_df.to_dict(orient="records"):
            latest_lookup[str(row["station_id"])] = SensorReading(
                station_id=str(row["station_id"]),
                pasture_id=str(row.get("pasture_id", "")),
                timestamp=pd.Timestamp(row["timestamp"]),
                air_temp_f=row.get("air_temp_f"),
                humidity_pct=row.get("humidity_pct"),
                pressure_hpa=row.get("pressure_hpa"),
                rainfall_in=row.get("rainfall_in"),
                soil_moisture_10cm=row.get("soil_moisture_10cm"),
                soil_moisture_30cm=row.get("soil_moisture_30cm"),
                soil_moisture_60cm=row.get("soil_moisture_60cm"),
                soil_temp_f=row.get("soil_temp_f"),
                water_tank_pct=row.get("water_tank_pct"),
                trough_level_pct=row.get("trough_level_pct"),
                battery_voltage=row.get("battery_voltage"),
                solar_voltage=row.get("solar_voltage"),
                signal_strength=row.get("signal_strength"),
                rssi=row.get("rssi"),
                snr=row.get("snr"),
                hop_count=row.get("hop_count"),
                firmware_version=str(row.get("firmware_version", "")),
                notes=str(row.get("notes", "")),
            )
    return [classify_station_status(station, latest_lookup.get(station.station_id), now=now, thresholds=thresholds) for station in stations]
