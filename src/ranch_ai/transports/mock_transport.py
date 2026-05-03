from __future__ import annotations

import hashlib

import pandas as pd

from ranch_ai.sensors.mock import build_mock_station_registry, generate_mock_sensor_readings
from ranch_ai.telemetry.encoder import encode_compact_json, encode_pipe_delimited
from ranch_ai.telemetry.packet_schema import RawPacket
from ranch_ai.transports.base import TransportClient


class MockTransportClient(TransportClient):
    def __init__(
        self,
        stations=None,
        readings=None,
        seed: int = 42,
        days: int = 7,
        base_lat: float = 29.606333,
        base_lon: float = -103.50975,
    ) -> None:
        self._connected = False
        self._index = 0
        self._stations = stations or build_mock_station_registry(base_lat=base_lat, base_lon=base_lon, pasture_id="CC-001")
        readings_payload = readings or generate_mock_sensor_readings(self._stations, seed=seed, days=days)
        self._readings = sorted(readings_payload, key=lambda reading: pd.Timestamp(reading.timestamp), reverse=True)
        self._packets = [self._reading_to_packet(reading, idx) for idx, reading in enumerate(self._readings)]

    def _reading_to_packet(self, reading, idx: int) -> RawPacket:
        payload_raw = encode_compact_json(reading) if idx % 2 == 0 else encode_pipe_delimited(reading)
        digest = hashlib.sha1(f"{reading.station_id}-{reading.timestamp.isoformat()}-{idx}".encode("utf-8")).hexdigest()[:12]
        return RawPacket(
            packet_id=f"pkt-{digest}",
            received_at=pd.Timestamp(reading.timestamp),
            source_transport="mock_transport",
            from_node=reading.station_id,
            to_node="BASE1",
            payload_raw=payload_raw,
            rssi=reading.rssi,
            snr=reading.snr,
            hop_count=reading.hop_count,
            channel="RangeIQ-Telemetry",
            decoded_ok=False,
            error_message="",
        )

    def connect(self) -> None:
        self._connected = True
        self._index = 0

    def disconnect(self) -> None:
        self._connected = False

    def read_packet(self) -> RawPacket | None:
        if not self._connected or self._index >= len(self._packets):
            return None
        packet = self._packets[self._index]
        self._index += 1
        return packet

    def publish_packet(self, packet: RawPacket) -> None:
        self._packets.append(packet)

    def is_connected(self) -> bool:
        return self._connected
