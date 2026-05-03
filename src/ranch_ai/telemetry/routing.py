from __future__ import annotations

from ranch_ai.sensors.schema import SensorStation
from ranch_ai.telemetry.packet_schema import RawPacket


def route_packet_to_station(raw_packet: RawPacket, station_lookup: dict[str, SensorStation]) -> SensorStation | None:
    return station_lookup.get(raw_packet.from_node) or station_lookup.get(raw_packet.to_node) or station_lookup.get(raw_packet.packet_id)
