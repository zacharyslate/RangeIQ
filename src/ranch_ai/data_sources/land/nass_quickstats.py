from __future__ import annotations

from typing import Any

from ranch_ai.data_sources.base import BaseDataSourceProvider


class NASSQuickStatsDataSource(BaseDataSourceProvider):
    name = "nass_quickstats"
    category = "agriculture"
    requires_key = True
    access_level = "free_key_required"
    commercial_safe = True
    citation_url = "https://quickstats.nass.usda.gov/api"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "USDA NASS Quick Stats is disabled in config/api_sources.yaml.")
        if not self.configured_key():
            return self._disabled_response(latitude, longitude, "USDA NASS Quick Stats requires USDA_NASS_API_KEY.")

        params = {
            "key": self.configured_key(),
            "format": "JSON",
            "source_desc": kwargs.get("source_desc", "SURVEY"),
            "sector_desc": kwargs.get("sector_desc", "ANIMALS & PRODUCTS"),
            "group_desc": kwargs.get("group_desc", "LIVESTOCK"),
            "commodity_desc": kwargs.get("commodity_desc", "CATTLE"),
            "year__GE": kwargs.get("year_start", "2020"),
            "agg_level_desc": kwargs.get("agg_level_desc", "COUNTY"),
            "state_alpha": kwargs.get("state_alpha"),
            "county_name": kwargs.get("county_name"),
        }
        if not params["state_alpha"] or not params["county_name"]:
            return self._disabled_response(
                latitude,
                longitude,
                "USDA NASS Quick Stats fetch_point currently needs state_alpha and county_name filters.",
            )

        try:
            raw, request_meta = self._request_json(
                url="https://quickstats.nass.usda.gov/api/api_GET/",
                params=params,
                cache_context={"kind": "quickstats", "params": params},
                cache_ttl_hours=24,
            )
            return self.normalize_response(raw, latitude=latitude, longitude=longitude, request_meta=request_meta)
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"USDA NASS Quick Stats request failed: {exc}")

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        request_meta = kwargs.get("request_meta", {})
        data_rows = raw.get("data", []) if isinstance(raw, dict) else []
        warnings = []
        if request_meta.get("stale_cache"):
            warnings.append("Using stale cached USDA NASS Quick Stats response because the live request failed.")
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={"rows": data_rows},
            raw_metadata={"row_count": len(data_rows), "cache_hit": request_meta.get("cache_hit", False)},
            warnings=warnings,
        )
