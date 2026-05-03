from __future__ import annotations

from typing import Any


COMPACT_KEY_MAP = {
    "n": "station_id",
    "ts": "timestamp",
    "t": "air_temp_f",
    "h": "humidity_pct",
    "p": "pressure_hpa",
    "r": "rainfall_in",
    "s10": "soil_moisture_10cm",
    "s30": "soil_moisture_30cm",
    "s60": "soil_moisture_60cm",
    "st": "soil_temp_f",
    "w": "water_tank_pct",
    "tr": "trough_level_pct",
    "b": "battery_voltage",
    "sv": "solar_voltage",
    "rs": "rssi",
    "sn": "snr",
    "hp": "hop_count",
    "fw": "firmware_version",
    "nt": "notes",
}

REVERSE_COMPACT_KEY_MAP = {value: key for key, value in COMPACT_KEY_MAP.items()}

PIPE_FIELD_ORDER = [
    "n",
    "t",
    "h",
    "p",
    "r",
    "s10",
    "s30",
    "s60",
    "st",
    "w",
    "tr",
    "b",
    "sv",
    "rs",
    "sn",
    "hp",
]


def expand_compact_keys(payload: dict[str, Any]) -> dict[str, Any]:
    expanded: dict[str, Any] = {}
    for key, value in payload.items():
        expanded[COMPACT_KEY_MAP.get(key, key)] = value
    return expanded


def compact_sensor_values(values: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in values.items():
        compact_key = REVERSE_COMPACT_KEY_MAP.get(key)
        if compact_key is None:
            continue
        compacted[compact_key] = value
    return compacted
