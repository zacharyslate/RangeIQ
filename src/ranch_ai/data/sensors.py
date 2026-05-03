from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


SENSOR_COLUMNS = [
    "station_id",
    "pasture_id",
    "timestamp",
    "air_temp_f",
    "humidity_pct",
    "pressure_hpa",
    "rainfall_in",
    "soil_moisture_10cm",
    "soil_moisture_30cm",
    "soil_temp_f",
    "battery_voltage",
    "signal_strength",
    "water_tank_pct",
    "trough_level_pct",
    "camera_status",
    "notes",
]


def celsius_to_fahrenheit(value: float) -> float:
    return value * 9 / 5 + 32


def mm_to_inches(value: float) -> float:
    return value / 25.4


def inches_to_mm(value: float) -> float:
    return value * 25.4


def normalize_sensor_dataframe(sensor_df: pd.DataFrame) -> pd.DataFrame:
    df = sensor_df.copy()

    if "air_temp_c" in df.columns and "air_temp_f" not in df.columns:
        df["air_temp_f"] = df["air_temp_c"].astype(float).apply(celsius_to_fahrenheit)
    if "rainfall_mm" in df.columns and "rainfall_in" not in df.columns:
        df["rainfall_in"] = df["rainfall_mm"].astype(float).apply(mm_to_inches)
    if "soil_temp_c" in df.columns and "soil_temp_f" not in df.columns:
        df["soil_temp_f"] = df["soil_temp_c"].astype(float).apply(celsius_to_fahrenheit)

    defaults = {
        "water_tank_pct": np.nan,
        "trough_level_pct": np.nan,
        "camera_status": "UNKNOWN",
        "notes": "",
    }
    for column, default_value in defaults.items():
        if column not in df.columns:
            df[column] = default_value

    for column in SENSOR_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[SENSOR_COLUMNS].sort_values(["station_id", "timestamp"]).reset_index(drop=True)


def generate_synthetic_sensor_readings(
    pastures: pd.DataFrame,
    weather_df: pd.DataFrame,
    soil_df: pd.DataFrame,
    seed: int = 42,
    days: int = 14,
    end_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Generate hourly mock sensor data for the operational dashboard and CSV backend."""
    rng = np.random.default_rng(seed + 47)
    end_timestamp = (end_time or pd.Timestamp.now(tz=None)).floor("h")
    hourly_index = pd.date_range(end=end_timestamp, periods=days * 24, freq="h")
    weather_latest = weather_df.sort_values("week_start").groupby("pasture_id", as_index=False).tail(1)
    weather_lookup = weather_latest.set_index("pasture_id")
    soil_lookup = soil_df.set_index("pasture_id")
    rows: list[dict[str, object]] = []

    for pasture_idx, pasture in pastures.reset_index(drop=True).iterrows():
        pasture_id = pasture["pasture_id"]
        weather_row = weather_lookup.loc[pasture_id]
        soil_row = soil_lookup.loc[pasture_id]

        dry_station = pasture_idx == min(2, len(pastures) - 1)
        low_battery_station = pasture_idx == 0
        offline_station = pasture_idx == 1 and len(pastures) > 1
        low_water_station = pasture_idx == min(3, len(pastures) - 1)
        low_signal_station = pasture_idx == min(4, len(pastures) - 1)

        air_temp_center_f = celsius_to_fahrenheit(float(weather_row["temp_avg_7d"]))
        soil_moisture_center = np.clip(
            float(weather_row["rainfall_7d"]) * 0.55 + float(soil_row["soil_water_capacity"]) * 0.12,
            8,
            36,
        )
        if dry_station:
            soil_moisture_center = max(8, soil_moisture_center - 12)

        water_tank_start = 78 - pasture_idx * 6
        if low_water_station:
            water_tank_start = 28

        battery_start = 4.08 - pasture_idx * 0.03
        if low_battery_station:
            battery_start = 3.46

        signal_start = -82 - pasture_idx * 4
        if low_signal_station:
            signal_start = -116

        effective_index = hourly_index
        if offline_station:
            effective_index = hourly_index[:-16]

        for step_idx, timestamp in enumerate(effective_index):
            hour = timestamp.hour
            diurnal = np.sin(((hour - 5) / 24) * 2 * np.pi)
            temp_f = air_temp_center_f + diurnal * 13 + rng.normal(0, 2.2)
            humidity = np.clip(48 - diurnal * 14 - (temp_f - 80) * 0.35 + rng.normal(0, 6), 10, 98)
            pressure = 1008 + rng.normal(0, 4.5)
            rainfall_roll = 0.0
            if rng.random() < 0.08:
                rainfall_roll = max(0.0, rng.gamma(1.8, 0.06))
            soil_moisture_30 = np.clip(
                soil_moisture_center
                + diurnal * 1.3
                + rng.normal(0, 1.6)
                + rainfall_roll * 38
                - step_idx * (0.01 if dry_station else 0.002),
                4,
                48,
            )
            soil_moisture_10 = np.clip(soil_moisture_30 + rng.normal(1.6, 2.0), 3, 55)
            soil_temp_f = temp_f * 0.9 + rng.normal(0, 2.0)
            battery = np.clip(battery_start - step_idx * (0.0026 if low_battery_station else 0.0003), 3.1, 4.2)
            signal = int(np.clip(signal_start + rng.normal(0, 3.8), -125, -62))
            water_tank_pct = np.clip(water_tank_start - step_idx * (0.05 if low_water_station else 0.015), 6, 100)
            trough_level_pct = np.clip(water_tank_pct - rng.normal(6, 5), 2, 100)
            camera_status = "OK"
            notes = ""

            if low_signal_station and rng.random() < 0.08:
                camera_status = "UNSTABLE"
                notes = "Intermittent cellular signal."

            rows.append(
                {
                    "station_id": f"ST-{pasture_id}",
                    "pasture_id": pasture_id,
                    "timestamp": timestamp,
                    "air_temp_f": round(float(temp_f), 2),
                    "humidity_pct": round(float(humidity), 2),
                    "pressure_hpa": round(float(pressure), 2),
                    "rainfall_in": round(float(rainfall_roll), 3),
                    "soil_moisture_10cm": round(float(soil_moisture_10), 2),
                    "soil_moisture_30cm": round(float(soil_moisture_30), 2),
                    "soil_temp_f": round(float(soil_temp_f), 2),
                    "battery_voltage": round(float(battery), 2),
                    "signal_strength": signal,
                    "water_tank_pct": round(float(water_tank_pct), 1),
                    "trough_level_pct": round(float(trough_level_pct), 1),
                    "camera_status": camera_status,
                    "notes": notes,
                }
            )

    return pd.DataFrame(rows, columns=SENSOR_COLUMNS)


def load_sensor_csv(path: str | Path) -> pd.DataFrame:
    return normalize_sensor_dataframe(pd.read_csv(path))


def aggregate_weekly_sensor_features(sensor_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sensor readings into pasture-week features for the pasture model."""
    weekly = normalize_sensor_dataframe(sensor_df)
    weekly["week_start"] = weekly["timestamp"].dt.to_period("W-SUN").apply(lambda period: period.start_time)

    grouped = (
        weekly.groupby(["pasture_id", "week_start"], as_index=False)[
            ["soil_moisture_10cm", "soil_moisture_30cm", "rainfall_in", "air_temp_f", "humidity_pct"]
        ]
        .agg(
            {
                "soil_moisture_10cm": "mean",
                "soil_moisture_30cm": "mean",
                "rainfall_in": "sum",
                "air_temp_f": "mean",
                "humidity_pct": "mean",
            }
        )
        .rename(columns={"rainfall_in": "sensor_rainfall_in", "air_temp_f": "sensor_air_temp_f"})
    )
    grouped["sensor_rainfall_mm"] = grouped["sensor_rainfall_in"].apply(inches_to_mm).round(2)
    return grouped


def save_sensor_schema(sensor_df: pd.DataFrame, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_sensor_dataframe(sensor_df)
    normalized.to_csv(destination, index=False)
    return destination
