from __future__ import annotations

from ranch_ai.storage.database import SensorNetworkStore


class PostgresStore(SensorNetworkStore):
    def create_tables(self) -> None:
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def reset(self) -> None:
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def save_raw_packet(self, raw_packet) -> None:
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def save_sensor_reading(self, reading) -> None:
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def upsert_station_status(self, status) -> None:
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def fetch_raw_packets(self, limit: int | None = None):
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def fetch_sensor_readings(self, limit: int | None = None):
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")

    def fetch_station_status(self):
        raise NotImplementedError("Postgres storage is scaffolded but not implemented in this MVP.")
