import copy

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.data.sensors import SENSOR_COLUMNS, generate_synthetic_sensor_readings
from ranch_ai.services.sensor_service import SensorService, classify_sensor_status


def test_sensor_status_classification_flags_offline_battery_and_signal():
    runtime_settings = copy.deepcopy(settings)
    now = pd.Timestamp("2026-04-26 15:00:00")
    pasture_lookup = {"P-101": "North Flats", "P-102": "Mesquite East", "P-103": "Cottonwood Draw"}
    sensor_df = pd.DataFrame(
        [
            {
                "station_id": "ST-P-101",
                "pasture_id": "P-101",
                "timestamp": now - pd.Timedelta(minutes=30),
                "air_temp_f": 84.0,
                "humidity_pct": 32.0,
                "pressure_hpa": 1009.0,
                "rainfall_in": 0.0,
                "soil_moisture_10cm": 19.0,
                "soil_moisture_30cm": 17.0,
                "soil_temp_f": 78.0,
                "battery_voltage": 3.42,
                "signal_strength": -95,
                "water_tank_pct": 62.0,
                "trough_level_pct": 54.0,
                "camera_status": "OK",
                "notes": "",
            },
            {
                "station_id": "ST-P-102",
                "pasture_id": "P-102",
                "timestamp": now - pd.Timedelta(hours=5),
                "air_temp_f": 83.0,
                "humidity_pct": 35.0,
                "pressure_hpa": 1007.0,
                "rainfall_in": 0.0,
                "soil_moisture_10cm": 21.0,
                "soil_moisture_30cm": 18.0,
                "soil_temp_f": 77.0,
                "battery_voltage": 3.88,
                "signal_strength": -112,
                "water_tank_pct": 40.0,
                "trough_level_pct": 38.0,
                "camera_status": "OK",
                "notes": "",
            },
            {
                "station_id": "ST-P-103",
                "pasture_id": "P-103",
                "timestamp": now - pd.Timedelta(hours=14),
                "air_temp_f": 200.0,
                "humidity_pct": 20.0,
                "pressure_hpa": 1006.0,
                "rainfall_in": 0.0,
                "soil_moisture_10cm": 14.0,
                "soil_moisture_30cm": 11.0,
                "soil_temp_f": 80.0,
                "battery_voltage": 3.91,
                "signal_strength": -88,
                "water_tank_pct": 33.0,
                "trough_level_pct": 30.0,
                "camera_status": "OK",
                "notes": "",
            },
        ],
        columns=SENSOR_COLUMNS,
    )

    status_df = classify_sensor_status(sensor_df, pasture_lookup=pasture_lookup, app_settings=runtime_settings, now=now)

    assert bool(status_df.loc[status_df["station_id"] == "ST-P-101", "low_battery"].iloc[0]) is True
    assert status_df.loc[status_df["station_id"] == "ST-P-102", "status"].iloc[0] == "STALE"
    assert bool(status_df.loc[status_df["station_id"] == "ST-P-102", "low_signal"].iloc[0]) is True
    assert status_df.loc[status_df["station_id"] == "ST-P-103", "status"].iloc[0] == "SENSOR ERROR"


def test_sensor_service_falls_back_to_mock_generation_for_missing_csv():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.sensors.provider = "csv"
    runtime_settings.sensors.csv_path = "data/sensors/does_not_exist.csv"

    pastures = pd.DataFrame(
        [
            {"pasture_id": "P-101", "name": "North Flats"},
            {"pasture_id": "P-102", "name": "Mesquite East"},
            {"pasture_id": "P-103", "name": "Cottonwood Draw"},
        ]
    )
    weather_df = pd.DataFrame(
        [
            {"pasture_id": "P-101", "week_start": pd.Timestamp("2026-04-21"), "rainfall_7d": 8.0, "temp_avg_7d": 22.0},
            {"pasture_id": "P-102", "week_start": pd.Timestamp("2026-04-21"), "rainfall_7d": 5.0, "temp_avg_7d": 24.0},
            {"pasture_id": "P-103", "week_start": pd.Timestamp("2026-04-21"), "rainfall_7d": 2.0, "temp_avg_7d": 25.0},
        ]
    )
    soil_df = pd.DataFrame(
        [
            {"pasture_id": "P-101", "soil_water_capacity": 24.0},
            {"pasture_id": "P-102", "soil_water_capacity": 22.0},
            {"pasture_id": "P-103", "soil_water_capacity": 18.0},
        ]
    )

    bundle = SensorService(runtime_settings).load_sensor_bundle(
        pastures=pastures,
        weather_df=weather_df,
        soil_df=soil_df,
        seed=42,
    )

    assert bundle.mode == "fallback-mock"
    assert not bundle.readings.empty
    assert not bundle.latest_status.empty
    assert len(bundle.latest_status["station_id"].unique()) == 3
