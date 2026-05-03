from __future__ import annotations

from pathlib import Path

from ranch_ai.config import settings
from ranch_ai.sensors.mock import build_mock_station_registry
from ranch_ai.sensors.registry import load_station_registry_yaml
from ranch_ai.sensors.schema import SensorStation


def load_station_config(path: str | Path | None = None) -> list[SensorStation]:
    registry_path = Path(path or settings.sensor_network.station_registry_path)
    if registry_path.exists():
        try:
            return load_station_registry_yaml(registry_path)
        except Exception:
            return build_mock_station_registry(
                base_lat=settings.ranch.latitude,
                base_lon=settings.ranch.longitude,
                pasture_id="CC-001",
                expected_interval_minutes=settings.sensor_network.expected_interval_minutes,
            )
    return build_mock_station_registry(
        base_lat=settings.ranch.latitude,
        base_lon=settings.ranch.longitude,
        pasture_id="CC-001",
        expected_interval_minutes=settings.sensor_network.expected_interval_minutes,
    )
