from __future__ import annotations

from abc import ABC, abstractmethod

from ranch_ai.telemetry.packet_schema import RawPacket


class TransportClient(ABC):
    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_packet(self) -> RawPacket | None:
        raise NotImplementedError

    def publish_packet(self, packet: RawPacket) -> None:
        raise NotImplementedError("This transport does not implement packet publishing yet.")

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError
