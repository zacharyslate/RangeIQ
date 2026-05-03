from __future__ import annotations

from ranch_ai.transports.base import TransportClient


class CellularTransportClient(TransportClient):
    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> None:
        raise NotImplementedError("Cellular ingestion is planned but not implemented yet.")

    def disconnect(self) -> None:
        self._connected = False

    def read_packet(self):
        return None

    def is_connected(self) -> bool:
        return self._connected
