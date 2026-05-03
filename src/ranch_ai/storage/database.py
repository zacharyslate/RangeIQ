from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ranch_ai.sensors.schema import SensorReading, StationStatus
from ranch_ai.telemetry.packet_schema import RawPacket


class SensorNetworkStore(ABC):
    @abstractmethod
    def create_tables(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_raw_packet(self, raw_packet: RawPacket) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_sensor_reading(self, reading: SensorReading) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_station_status(self, status: StationStatus) -> None:
        raise NotImplementedError

    @abstractmethod
    def fetch_raw_packets(self, limit: int | None = None) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_sensor_readings(self, limit: int | None = None) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_station_status(self) -> pd.DataFrame:
        raise NotImplementedError
