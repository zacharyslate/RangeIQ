from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd


TrendLabel = Literal["increasing", "stable", "declining", "unknown"]


@dataclass
class VegetationScore:
    score: float | None
    category: str
    explanation: str
    drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VegetationSummary:
    aoi_id: str
    date_range: dict[str, str]
    ndvi: dict[str, Any]
    rap: dict[str, Any]
    rangeiq_score: dict[str, Any]
    ndvi_provider: str = "mock"
    rap_provider: str = "mock"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VegetationArtifacts:
    monthly_features: pd.DataFrame
    ndvi_series: pd.DataFrame
    rap_cover_series: pd.DataFrame
    rap_production_series: pd.DataFrame
    rap_production_16day_series: pd.DataFrame
    summary_frame: pd.DataFrame
    summaries: list[VegetationSummary]
    warnings: list[str] = field(default_factory=list)

    def summary_for_pasture(self, pasture_id: str) -> VegetationSummary | None:
        for summary in self.summaries:
            if summary.aoi_id == pasture_id:
                return summary
        return None

    def summary_dicts(self) -> list[dict[str, Any]]:
        return [summary.to_dict() for summary in self.summaries]
