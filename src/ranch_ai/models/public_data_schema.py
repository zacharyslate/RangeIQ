from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ranch_ai.vegetation.vegetation_types import VegetationArtifacts


@dataclass
class PublicSourceStatus:
    component: str
    configured_provider: str
    active_provider: str
    mode: str
    status: str
    citation_url: str
    loaded_at: pd.Timestamp | None = None
    cache_path: str | None = None
    cache_saved_at: pd.Timestamp | None = None
    cache_expires_at: pd.Timestamp | None = None
    cache_age_hours: float | None = None


@dataclass
class PublicDataBundle:
    historical_weather: pd.DataFrame
    soils: pd.DataFrame
    drought: pd.DataFrame
    vegetation: pd.DataFrame
    vegetation_artifacts: VegetationArtifacts | None = None
    source_status: list[PublicSourceStatus] = field(default_factory=list)
    loaded_at: pd.Timestamp = field(default_factory=pd.Timestamp.now)


@dataclass
class TrainingDatasetArtifacts:
    dataset: pd.DataFrame
    summary: dict[str, Any]
