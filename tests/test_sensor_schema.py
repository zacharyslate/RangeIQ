import pandas as pd

from ranch_ai.sensors.schema import SensorReading, SensorStation


def test_sensor_schema_dataclasses_serialize_to_records():
    reading = SensorReading(
        station_id="NP1",
        pasture_id="CC-001",
        timestamp=pd.Timestamp("2026-04-26 10:00:00"),
        air_temp_f=91.4,
        humidity_pct=22.0,
        battery_voltage=3.91,
    )
    station = SensorStation(
        station_id="NP1",
        station_name="North Pasture Soil Station",
        pasture_id="CC-001",
        station_type="soil",
        latitude=29.608033,
        longitude=-103.51115,
        installed_at=pd.Timestamp("2026-03-15 08:00:00"),
        expected_interval_minutes=60,
        sensors=["air_temp_f", "soil_moisture_10cm"],
    )

    reading_record = reading.to_record()
    station_record = station.to_record()

    assert reading_record["station_id"] == "NP1"
    assert reading_record["air_temp_f"] == 91.4
    assert station_record["station_name"] == "North Pasture Soil Station"
    assert "soil_moisture_10cm" in station_record["sensors"]
