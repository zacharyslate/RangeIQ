from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MeshNode:
    node_id: str
    station_id: str
    role: str
    last_seen: pd.Timestamp | None = None
    rssi: float | None = None
    snr: float | None = None
    active: bool = True
    notes: str = ""
