from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.data.public_sources import USDroughtMonitorProvider
from ranch_ai.data_sources.base import BaseDataSourceProvider


class DroughtMonitorDataSource(BaseDataSourceProvider):
    name = "drought_monitor"
    category = "drought"
    requires_key = False
    access_level = "free_open_government"
    commercial_safe = True
    citation_url = "https://www.drought.gov/data-maps-tools/us-drought-monitor"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "U.S. Drought Monitor is disabled in config/api_sources.yaml.")

        start_date = pd.Timestamp(kwargs.get("start_date", pd.Timestamp.today() - pd.Timedelta(weeks=26))).strftime("%Y-%m-%d")
        end_date = pd.Timestamp(kwargs.get("end_date", pd.Timestamp.today())).strftime("%Y-%m-%d")
        provider = USDroughtMonitorProvider(timeout_seconds=int(self.timeout_seconds))
        try:
            frame = provider.get_weekly_drought(latitude, longitude, start_date, end_date)
            history = frame.to_dict(orient="records")
            return self.normalize_response(history, latitude=latitude, longitude=longitude)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"U.S. Drought Monitor request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        latest = raw[-1] if raw else {}
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={
                "latest": latest,
                "history": raw,
            },
            units={
                "coverage": "%",
                "max_intensity": "%",
            },
            raw_metadata={"row_count": len(raw)},
            warnings=[],
        )
