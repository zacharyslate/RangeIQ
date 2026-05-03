from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class AlertBundle:
    alerts: pd.DataFrame
    provider_name: str
    mode: str
    source_message: str
    loaded_at: pd.Timestamp
