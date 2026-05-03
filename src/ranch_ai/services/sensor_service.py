from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.data.sensors import (
    SENSOR_COLUMNS,
    generate_synthetic_sensor_readings,
    load_sensor_csv,
    normalize_sensor_dataframe,
)
from ranch_ai.models.sensor_schema import SensorBundle, SensorStatus


def _derive_station_name(station_id: str, pasture_lookup: dict[str, str]) -> str:
    pasture_id = station_id.replace("ST-", "", 1)
    pasture_name = pasture_lookup.get(pasture_id, pasture_id)
    return f"{pasture_name} Station"


def _has_sensor_error(row: pd.Series) -> bool:
    checks = {
        "air_temp_f": (-40, 150),
        "humidity_pct": (0, 100),
        "pressure_hpa": (850, 1100),
        "soil_moisture_10cm": (0, 100),
        "soil_moisture_30cm": (0, 100),
        "water_tank_pct": (0, 100),
        "trough_level_pct": (0, 100),
    }
    for column, bounds in checks.items():
        value = row.get(column)
        if pd.isna(value):
            continue
        if value < bounds[0] or value > bounds[1]:
            return True
    return False


def classify_sensor_status(
    sensor_df: pd.DataFrame,
    pasture_lookup: dict[str, str],
    app_settings: Settings = settings,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if sensor_df.empty:
        return pd.DataFrame()

    normalized = normalize_sensor_dataframe(sensor_df)
    current_time = now or pd.Timestamp.now()
    latest_rows = normalized.sort_values("timestamp").groupby("station_id", as_index=False).tail(1).reset_index(drop=True)
    status_rows: list[dict[str, object]] = []

    for _, row in latest_rows.iterrows():
        age_minutes = (current_time - row["timestamp"]).total_seconds() / 60
        low_battery = pd.notna(row["battery_voltage"]) and row["battery_voltage"] < app_settings.sensors.low_battery_voltage
        low_signal = pd.notna(row["signal_strength"]) and row["signal_strength"] < app_settings.sensors.low_signal_threshold
        sensor_error = _has_sensor_error(row)

        if sensor_error:
            status = "SENSOR ERROR"
        elif age_minutes >= app_settings.sensors.offline_after_minutes:
            status = "OFFLINE"
        elif age_minutes >= app_settings.sensors.stale_after_minutes:
            status = "STALE"
        else:
            status = "ONLINE"

        sensor_status = SensorStatus(
            station_id=str(row["station_id"]),
            pasture_id=str(row["pasture_id"]),
            station_name=_derive_station_name(str(row["station_id"]), pasture_lookup),
            last_contact=pd.Timestamp(row["timestamp"]),
            status=status,
            data_freshness_minutes=round(age_minutes, 1),
            battery_voltage=None if pd.isna(row["battery_voltage"]) else float(row["battery_voltage"]),
            signal_strength=None if pd.isna(row["signal_strength"]) else float(row["signal_strength"]),
            low_battery=bool(low_battery),
            low_signal=bool(low_signal),
            sensor_error=bool(sensor_error),
            water_tank_pct=None if pd.isna(row["water_tank_pct"]) else float(row["water_tank_pct"]),
            trough_level_pct=None if pd.isna(row["trough_level_pct"]) else float(row["trough_level_pct"]),
            camera_status=str(row["camera_status"]),
        )
        record = asdict(sensor_status)
        record.update(
            {
                "air_temp_f": row["air_temp_f"],
                "humidity_pct": row["humidity_pct"],
                "rainfall_in": row["rainfall_in"],
                "soil_moisture_10cm": row["soil_moisture_10cm"],
                "soil_moisture_30cm": row["soil_moisture_30cm"],
                "soil_temp_f": row["soil_temp_f"],
                "pressure_hpa": row["pressure_hpa"],
                "notes": row["notes"],
            }
        )
        status_rows.append(record)

    return pd.DataFrame(status_rows).sort_values(["status", "station_id"]).reset_index(drop=True)


def build_sensor_alerts(status_df: pd.DataFrame) -> pd.DataFrame:
    if status_df.empty:
        return pd.DataFrame(columns=["station_id", "severity", "message"])

    alert_rows: list[dict[str, str]] = []
    for row in status_df.itertuples(index=False):
        if row.status in {"OFFLINE", "SENSOR ERROR"}:
            alert_rows.append({"station_id": row.station_id, "severity": "HIGH", "message": f"{row.station_name} is {row.status.lower()}."})
        if row.low_battery:
            alert_rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_name} battery is low ({row.battery_voltage}V)."})
        if row.low_signal:
            alert_rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_name} has weak signal ({row.signal_strength:.0f} dBm)."})
        if pd.notna(row.water_tank_pct) and row.water_tank_pct < 25:
            alert_rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_name} water tank is below 25%."})
        if pd.notna(row.soil_moisture_30cm) and row.soil_moisture_30cm < 15:
            alert_rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_name} reports low deep soil moisture."})

    return pd.DataFrame(alert_rows)


class SensorService:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings

    def load_sensor_bundle(
        self,
        pastures: pd.DataFrame,
        weather_df: pd.DataFrame,
        soil_df: pd.DataFrame,
        provider: str | None = None,
        seed: int | None = None,
    ) -> SensorBundle:
        active_provider = (provider or self.settings.sensors.provider).lower()
        loaded_at = pd.Timestamp.now()
        source_message = ""

        if active_provider == "csv":
            try:
                readings = load_sensor_csv(self.settings.sensors.csv_path)
                mode = "csv"
                source_message = f"Loaded CSV sensor data from {self.settings.sensors.csv_path}"
            except Exception:
                readings = generate_synthetic_sensor_readings(
                    pastures,
                    weather_df,
                    soil_df,
                    seed=seed or self.settings.random_seed,
                    days=self.settings.sensors.mock_days,
                )
                mode = "fallback-mock"
                source_message = "Sensor CSV unavailable; using mock sensor history."
        else:
            readings = generate_synthetic_sensor_readings(
                pastures,
                weather_df,
                soil_df,
                seed=seed or self.settings.random_seed,
                days=self.settings.sensors.mock_days,
            )
            mode = "mock"
            source_message = "Using mock sensor history."

        pasture_lookup = dict(zip(pastures["pasture_id"], pastures["name"]))
        latest_status = classify_sensor_status(readings, pasture_lookup=pasture_lookup, app_settings=self.settings, now=loaded_at)
        alerts = build_sensor_alerts(latest_status)

        return SensorBundle(
            readings=normalize_sensor_dataframe(readings),
            latest_status=latest_status,
            alerts=alerts,
            provider_name=active_provider,
            mode=mode,
            source_message=source_message,
            loaded_at=loaded_at,
        )

