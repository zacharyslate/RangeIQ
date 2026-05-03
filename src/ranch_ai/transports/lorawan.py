from __future__ import annotations

from ranch_ai.transports.base import TransportClient


class LoRaWANTransportClient(TransportClient):
    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> None:
        raise NotImplementedError("LoRaWAN ingestion is planned but not implemented yet.")

    def disconnect(self) -> None:
        self._connected = False

    def read_packet(self):
        return None

    def is_connected(self) -> bool:
        return self._connected
