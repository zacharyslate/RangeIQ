from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class RawPacket:
    packet_id: str
    received_at: pd.Timestamp
    source_transport: str
    from_node: str
    to_node: str
    payload_raw: str
    rssi: float | None = None
    snr: float | None = None
    hop_count: int | None = None
    channel: str = ""
    decoded_ok: bool = False
    error_message: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["received_at"] = pd.Timestamp(self.received_at)
        return record


@dataclass
class DecodedTelemetryPacket:
    station_id: str
    timestamp: pd.Timestamp
    values: dict[str, Any] = field(default_factory=dict)
    packet_format: str = ""
    firmware_version: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = pd.Timestamp(self.timestamp)
        return record
