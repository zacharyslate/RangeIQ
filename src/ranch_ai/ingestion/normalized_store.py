from __future__ import annotations

from ranch_ai.sensors.schema import SensorReading, StationStatus
from ranch_ai.storage.database import SensorNetworkStore


def save_sensor_reading(store: SensorNetworkStore, reading: SensorReading) -> None:
    store.save_sensor_reading(reading)


def save_station_status(store: SensorNetworkStore, status: StationStatus) -> None:
    store.upsert_station_status(status)
