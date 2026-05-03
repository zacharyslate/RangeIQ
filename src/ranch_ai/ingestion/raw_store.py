from __future__ import annotations

from ranch_ai.storage.database import SensorNetworkStore
from ranch_ai.telemetry.packet_schema import RawPacket


def save_raw_packet(store: SensorNetworkStore, packet: RawPacket) -> None:
    store.save_raw_packet(packet)
