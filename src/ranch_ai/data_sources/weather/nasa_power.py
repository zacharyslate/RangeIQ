from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.data.public_sources import NasaPowerHistoricalWeatherProvider
from ranch_ai.data_sources.base import BaseDataSourceProvider


class NasaPowerDataSource(BaseDataSourceProvider):
    name = "nasa_power"
    category = "weather"
    requires_key = False
    access_level = "free_open_government"
    commercial_safe = True
    citation_url = "https://power.larc.nasa.gov/docs/services/api/"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "NASA POWER is disabled in config/api_sources.yaml.")

        start_date = pd.Timestamp(kwargs.get("start_date", pd.Timestamp.today() - pd.Timedelta(days=30))).strftime("%Y-%m-%d")
        end_date = pd.Timestamp(kwargs.get("end_date", pd.Timestamp.today())).strftime("%Y-%m-%d")
        provider = NasaPowerHistoricalWeatherProvider(timeout_seconds=int(self.timeout_seconds))
        try:
            history = provider.get_daily_history(latitude, longitude, start_date, end_date)
            raw = history.to_dict(orient="records")
            return self.normalize_response(raw, latitude=latitude, longitude=longitude, start_date=start_date, end_date=end_date)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"NASA POWER request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        data = {
            "history": raw,
            "start_date": kwargs.get("start_date"),
            "end_date": kwargs.get("end_date"),
        }
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data=data,
            units={
                "temperature": "F",
                "precipitation": "in",
                "humidity": "%",
                "wind_speed": "mph",
            },
            raw_metadata={"row_count": len(raw)},
            warnings=[],
        )
