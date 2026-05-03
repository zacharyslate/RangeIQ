from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from ranch_ai.sensors.schema import SensorReading


def validate_timestamp(value: Any) -> bool:
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return False
    return not pd.isna(parsed)


def validate_required_fields(payload: dict[str, Any], required_fields: Iterable[str]) -> list[str]:
    missing = [field for field in required_fields if payload.get(field) in {None, ""}]
    return [f"Missing required field: {field}" for field in missing]


def _validate_range(field_name: str, value: float | None, lower: float, upper: float) -> list[str]:
    if value is None or pd.isna(value):
        return []
    if lower <= float(value) <= upper:
        return []
    return [f"{field_name}={value} is outside the expected range {lower} to {upper}."]


def validate_sensor_reading(reading: SensorReading) -> list[str]:
    warnings: list[str] = []
    if not validate_timestamp(reading.timestamp):
        warnings.append("timestamp is not parseable.")

    warnings.extend(_validate_range("air_temp_f", reading.air_temp_f, -60, 170))
    warnings.extend(_validate_range("humidity_pct", reading.humidity_pct, 0, 100))
    warnings.extend(_validate_range("soil_moisture_10cm", reading.soil_moisture_10cm, 0, 100))
    warnings.extend(_validate_range("soil_moisture_30cm", reading.soil_moisture_30cm, 0, 100))
    warnings.extend(_validate_range("soil_moisture_60cm", reading.soil_moisture_60cm, 0, 100))
    warnings.extend(_validate_range("water_tank_pct", reading.water_tank_pct, 0, 100))
    warnings.extend(_validate_range("trough_level_pct", reading.trough_level_pct, 0, 100))
    warnings.extend(_validate_range("battery_voltage", reading.battery_voltage, 2.5, 8.5))
    warnings.extend(_validate_range("solar_voltage", reading.solar_voltage, 0, 24))
    return warnings
