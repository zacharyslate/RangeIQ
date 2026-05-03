from __future__ import annotations

import json
from typing import Any

import pandas as pd

from ranch_ai.sensors.schema import SensorReading, SensorStation
from ranch_ai.telemetry.compact_formats import PIPE_FIELD_ORDER, expand_compact_keys
from ranch_ai.telemetry.packet_schema import DecodedTelemetryPacket


def _coerce_numeric(value: Any) -> Any:
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        raw = str(value).strip()
        if raw == "":
            return None
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return value


def parse_compact_json(payload: str) -> DecodedTelemetryPacket:
    parsed = json.loads(payload)
    expanded = {key: _coerce_numeric(value) for key, value in expand_compact_keys(parsed).items()}
    station_id = str(expanded.pop("station_id"))
    timestamp_value = expanded.pop("timestamp", pd.NaT)
    timestamp = pd.Timestamp(timestamp_value) if timestamp_value is not pd.NaT else pd.NaT
    firmware_version = str(expanded.pop("firmware_version", ""))
    return DecodedTelemetryPacket(
        station_id=station_id,
        timestamp=timestamp,
        values=expanded,
        packet_format="compact_json",
        firmware_version=firmware_version,
    )


def parse_pipe_delimited(payload: str) -> DecodedTelemetryPacket:
    parts = [part.strip() for part in payload.strip().split("|")]
    if len(parts) < 2:
        raise ValueError("Pipe-delimited telemetry payload must contain at least station id and one value.")
    compact_payload = {PIPE_FIELD_ORDER[idx]: parts[idx] for idx in range(min(len(parts), len(PIPE_FIELD_ORDER)))}
    expanded = {key: _coerce_numeric(value) for key, value in expand_compact_keys(compact_payload).items()}
    station_id = str(expanded.pop("station_id"))
    timestamp_value = expanded.pop("timestamp", pd.NaT)
    timestamp = pd.Timestamp(timestamp_value) if timestamp_value is not pd.NaT else pd.NaT
    firmware_version = str(expanded.pop("firmware_version", ""))
    return DecodedTelemetryPacket(
        station_id=station_id,
        timestamp=timestamp,
        values=expanded,
        packet_format="pipe_delimited",
        firmware_version=firmware_version,
    )


def parse_packet(payload: str) -> DecodedTelemetryPacket:
    stripped = payload.strip()
    if stripped.startswith("{"):
        return parse_compact_json(stripped)
    if "|" in stripped:
        return parse_pipe_delimited(stripped)
    raise ValueError("Unsupported telemetry payload format.")


def convert_decoded_packet_to_sensor_reading(
    packet: DecodedTelemetryPacket,
    station_lookup: dict[str, SensorStation] | None = None,
) -> SensorReading:
    station_lookup = station_lookup or {}
    station = station_lookup.get(packet.station_id)
    pasture_id = station.pasture_id if station is not None else str(packet.values.get("pasture_id", "UNASSIGNED"))
    return SensorReading(
        station_id=packet.station_id,
        pasture_id=pasture_id,
        timestamp=pd.Timestamp(packet.timestamp),
        air_temp_f=packet.values.get("air_temp_f"),
        humidity_pct=packet.values.get("humidity_pct"),
        pressure_hpa=packet.values.get("pressure_hpa"),
        rainfall_in=packet.values.get("rainfall_in"),
        soil_moisture_10cm=packet.values.get("soil_moisture_10cm"),
        soil_moisture_30cm=packet.values.get("soil_moisture_30cm"),
        soil_moisture_60cm=packet.values.get("soil_moisture_60cm"),
        soil_temp_f=packet.values.get("soil_temp_f"),
        water_tank_pct=packet.values.get("water_tank_pct"),
        trough_level_pct=packet.values.get("trough_level_pct"),
        battery_voltage=packet.values.get("battery_voltage"),
        solar_voltage=packet.values.get("solar_voltage"),
        signal_strength=packet.values.get("signal_strength"),
        rssi=packet.values.get("rssi"),
        snr=packet.values.get("snr"),
        hop_count=packet.values.get("hop_count"),
        firmware_version=packet.firmware_version,
        notes=str(packet.values.get("notes", "")),
    )
