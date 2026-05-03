from __future__ import annotations

import pandas as pd

from ranch_ai.sensors.schema import SensorReading, SensorStation
from ranch_ai.sensors.validation import validate_sensor_reading
from ranch_ai.telemetry.parser import convert_decoded_packet_to_sensor_reading, parse_packet
from ranch_ai.telemetry.packet_schema import RawPacket


def process_raw_packet(
    raw_packet: RawPacket,
    station_lookup: dict[str, SensorStation] | None = None,
) -> tuple[SensorReading | None, list[str]]:
    try:
        decoded = parse_packet(raw_packet.payload_raw)
        reading = convert_decoded_packet_to_sensor_reading(decoded, station_lookup=station_lookup)
        if raw_packet.rssi is not None and reading.rssi is None:
            reading.rssi = raw_packet.rssi
        if raw_packet.snr is not None and reading.snr is None:
            reading.snr = raw_packet.snr
        if raw_packet.hop_count is not None and reading.hop_count is None:
            reading.hop_count = raw_packet.hop_count
        if raw_packet.received_at is not None and pd.isna(reading.timestamp):
            reading.timestamp = pd.Timestamp(raw_packet.received_at)
        warnings = validate_sensor_reading(reading)
        raw_packet.decoded_ok = True
        raw_packet.error_message = ""
        return reading, warnings
    except Exception as exc:
        raw_packet.decoded_ok = False
        raw_packet.error_message = str(exc)
        return None, [str(exc)]
