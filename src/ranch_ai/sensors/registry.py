from __future__ import annotations

from pathlib import Path

import pandas as pd

from ranch_ai.config import yaml
from ranch_ai.sensors.schema import SensorStation


def stations_to_dataframe(stations: list[SensorStation]) -> pd.DataFrame:
    return pd.DataFrame([station.to_record() for station in stations])


def build_station_lookup(stations: list[SensorStation]) -> dict[str, SensorStation]:
    return {station.station_id: station for station in stations}


def load_station_registry_yaml(path: str | Path) -> list[SensorStation]:
    source = Path(path)
    if yaml is None:
        raise RuntimeError("PyYAML is not installed; station_registry YAML loading is currently unavailable.")
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    stations_payload = payload.get("stations", {})
    stations: list[SensorStation] = []
    for station_id, config in stations_payload.items():
        sensors_raw = config.get("sensors", [])
        if isinstance(sensors_raw, str):
            sensors_raw = [sensor.strip() for sensor in sensors_raw.split(",") if sensor.strip()]
        stations.append(
            SensorStation(
                station_id=station_id,
                station_name=str(config.get("station_name", station_id)),
                pasture_id=str(config.get("pasture_id", "")),
                station_type=str(config.get("station_type", "experimental")),
                latitude=float(config.get("latitude", 0.0)),
                longitude=float(config.get("longitude", 0.0)),
                installed_at=pd.Timestamp(config.get("installed_at", pd.Timestamp.now())),
                expected_interval_minutes=int(config.get("expected_interval_minutes", 60)),
                sensors=list(sensors_raw),
                active=bool(config.get("active", True)),
                notes=str(config.get("notes", "")),
            )
        )
    return stations
