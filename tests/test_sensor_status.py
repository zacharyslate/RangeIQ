import pandas as pd

from ranch_ai.sensors.mock import build_mock_station_registry, generate_mock_sensor_readings, sensor_readings_to_dataframe
from ranch_ai.sensors.status import SensorStatusThresholds, build_station_status_table


def test_station_status_classification_flags_offline_low_battery_and_low_signal():
    stations = build_mock_station_registry(29.606333, -103.50975, pasture_id="CC-001", expected_interval_minutes=60)
    readings = generate_mock_sensor_readings(stations, seed=42, days=7, end_time=pd.Timestamp("2026-04-26 18:00:00"))
    readings_df = sensor_readings_to_dataframe(readings)

    statuses = build_station_status_table(
        stations,
        readings_df,
        now=pd.Timestamp("2026-04-26 18:00:00"),
        thresholds=SensorStatusThresholds(stale_after_minutes=180, offline_after_minutes=720, low_battery_voltage=3.5, low_signal_rssi=-115, low_water_tank_pct=25),
    )
    status_lookup = {status.station_id: status for status in statuses}

    assert status_lookup["NP1"].status == "ONLINE"
    assert status_lookup["SP1"].status in {"STALE", "OFFLINE"}
    assert status_lookup["WT1"].battery_status == "LOW_BATTERY"
    assert status_lookup["RLY1"].signal_status == "LOW_SIGNAL"
