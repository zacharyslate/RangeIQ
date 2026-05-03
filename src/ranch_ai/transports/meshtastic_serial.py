from __future__ import annotations

from dataclasses import dataclass

from ranch_ai.transports.base import TransportClient

try:  # pragma: no cover - optional dependency placeholder
    import serial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency placeholder
    serial = None


@dataclass
class MeshtasticSerialClient(TransportClient):
    port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200

    def __post_init__(self) -> None:
        self._connected = False

    def connect(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed yet. Install it later when Meshtastic serial ingestion is implemented.")
        # TODO: Open the Meshtastic serial node and stream decoded packets into RawPacket objects.
        raise NotImplementedError("Meshtastic serial ingestion is scaffolded but not implemented in this MVP.")

    def disconnect(self) -> None:
        self._connected = False

    def read_packet(self):
        # TODO: Read the next Meshtastic serial packet and normalize it into RawPacket.
        return None

    def is_connected(self) -> bool:
        return self._connected
