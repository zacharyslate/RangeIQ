import pandas as pd

from ranch_ai.sensors.schema import SensorReading
from ranch_ai.telemetry.encoder import encode_compact_json, encode_pipe_delimited


def test_packet_encoder_outputs_expected_formats():
    reading = SensorReading(
        station_id="NP1",
        pasture_id="CC-001",
        timestamp=pd.Timestamp("2026-04-26 10:00:00"),
        air_temp_f=91.4,
        humidity_pct=22,
        pressure_hpa=1007,
        rainfall_in=0.0,
        soil_moisture_10cm=13.2,
        soil_moisture_30cm=18.5,
        water_tank_pct=73,
        battery_voltage=3.91,
    )

    json_payload = encode_compact_json(reading)
    pipe_payload = encode_pipe_delimited(reading)

    assert '"n":"NP1"' in json_payload
    assert '"t":91.4' in json_payload
    assert pipe_payload.startswith("NP1|91.4|22|1007")
