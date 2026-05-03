from __future__ import annotations

from dataclasses import replace

from ranch_ai.sensors.schema import SensorReading


def apply_calibration(reading: SensorReading, offsets: dict[str, float] | None = None) -> SensorReading:
    """Apply simple additive calibration offsets to a reading."""
    offsets = offsets or {}
    updates = {}
    for field_name, offset in offsets.items():
        if hasattr(reading, field_name):
            current_value = getattr(reading, field_name)
            if current_value is not None:
                updates[field_name] = float(current_value) + float(offset)
    return replace(reading, **updates) if updates else reading
