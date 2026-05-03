from __future__ import annotations

from ranch_ai.telemetry.packet_schema import DecodedTelemetryPacket
from ranch_ai.telemetry.parser import parse_packet


def decode_payload(payload: str) -> DecodedTelemetryPacket:
    return parse_packet(payload)
