from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd

from ranch_ai.telemetry.compact_formats import PIPE_FIELD_ORDER, compact_sensor_values


def _reading_to_dict(reading: Any) -> dict[str, Any]:
    if is_dataclass(reading):
        payload = asdict(reading)
    else:
        payload = dict(reading)
    timestamp = payload.get("timestamp")
    if timestamp is not None and not pd.isna(timestamp):
        payload["timestamp"] = pd.Timestamp(timestamp).isoformat()
    return payload


def encode_compact_json(reading: Any) -> str:
    payload = _reading_to_dict(reading)
    compact = compact_sensor_values(payload)
    if "station_id" in payload:
        compact["n"] = payload["station_id"]
    if payload.get("timestamp"):
        compact["ts"] = payload["timestamp"]
    filtered = {key: value for key, value in compact.items() if value is not None and value != "" and value != []}
    return json.dumps(filtered, separators=(",", ":"))


def encode_pipe_delimited(reading: Any) -> str:
    payload = _reading_to_dict(reading)
    compact = compact_sensor_values(payload)
    compact["n"] = payload.get("station_id", "")
    values: list[str] = []
    for field_name in PIPE_FIELD_ORDER:
        value = compact.get(field_name)
        values.append("" if value is None or value == "" else str(value))
    while values and values[-1] == "":
        values.pop()
    return "|".join(values)
