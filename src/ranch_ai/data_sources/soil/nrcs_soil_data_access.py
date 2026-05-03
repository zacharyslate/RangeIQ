from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.data.public_sources import USDASoilDataAccessProvider
from ranch_ai.data_sources.base import BaseDataSourceProvider


class NRCSSoilDataAccessDataSource(BaseDataSourceProvider):
    name = "nrcs_soil_data_access"
    category = "soil"
    requires_key = False
    access_level = "free_open_government"
    commercial_safe = True
    citation_url = "https://sdmdataaccess.nrcs.usda.gov/"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "NRCS Soil Data Access is disabled in config/api_sources.yaml.")

        provider = USDASoilDataAccessProvider(timeout_seconds=int(self.timeout_seconds))
        pastures = pd.DataFrame(
            [
                {
                    "pasture_id": kwargs.get("pasture_id", "POINT-1"),
                    "centroid_lat": latitude,
                    "centroid_lon": longitude,
                    "acres": kwargs.get("acres", 1.0),
                }
            ]
        )
        try:
            frame = provider.get_pasture_soils(pastures)
            row = frame.iloc[0].to_dict() if not frame.empty else {}
            return self.normalize_response(row, latitude=latitude, longitude=longitude)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"NRCS Soil Data Access request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={
                "soil_type": raw.get("public_soil_type"),
                "available_water_capacity_in": raw.get("public_available_water_capacity_in"),
                "range_prod_index": raw.get("public_range_prod_index"),
                "soil_drainage_class": raw.get("public_soil_drainage_class"),
            },
            units={"available_water_capacity": "in"},
            raw_metadata={"source_label": raw.get("source")},
            warnings=[],
        )
