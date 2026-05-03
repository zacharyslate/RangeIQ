import pandas as pd
import pytest

from ranch_ai.sensors.schema import SensorStation
from ranch_ai.telemetry.parser import convert_decoded_packet_to_sensor_reading, parse_packet


def test_parse_compact_json_packet():
    packet = parse_packet('{"n":"NP1","t":91.4,"h":22,"p":1007,"r":0.00,"s10":13.2,"s30":18.5,"w":73,"b":3.91}')

    assert packet.station_id == "NP1"
    assert packet.packet_format == "compact_json"
    assert packet.values["air_temp_f"] == 91.4
    assert packet.values["soil_moisture_30cm"] == 18.5


def test_parse_pipe_delimited_packet():
    packet = parse_packet("NP1|91.4|22|1007|0.00|13.2|18.5|73|3.91")

    assert packet.station_id == "NP1"
    assert packet.packet_format == "pipe_delimited"
    assert packet.values["air_temp_f"] == 91.4
    assert packet.values["humidity_pct"] == 22


def test_invalid_packet_raises_value_error():
    with pytest.raises(ValueError):
        parse_packet("not-a-supported-packet")


def test_convert_decoded_packet_to_sensor_reading_uses_station_registry():
    packet = parse_packet('{"n":"NP1","t":88.1,"h":24,"b":3.88}')
    station = SensorStation(
        station_id="NP1",
        station_name="North Pasture Soil Station",
        pasture_id="CC-001",
        station_type="soil",
        latitude=29.6,
        longitude=-103.5,
        installed_at=pd.Timestamp("2026-03-15"),
        expected_interval_minutes=60,
    )

    reading = convert_decoded_packet_to_sensor_reading(packet, station_lookup={"NP1": station})

    assert reading.pasture_id == "CC-001"
    assert reading.air_temp_f == 88.1
