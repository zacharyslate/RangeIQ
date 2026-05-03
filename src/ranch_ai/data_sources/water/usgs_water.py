from __future__ import annotations

from math import radians, sin, cos, sqrt, atan2
from typing import Any

from ranch_ai.data_sources.base import BaseDataSourceProvider


def _miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_miles = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return earth_radius_miles * c


class USGSWaterDataSource(BaseDataSourceProvider):
    name = "usgs_water"
    category = "water"
    requires_key = False
    access_level = "free_open_government_optional_key"
    commercial_safe = True
    citation_url = "https://api.waterdata.usgs.gov/docs/"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "USGS Water is disabled in config/api_sources.yaml.")

        api_key = self.configured_key()
        bbox_buffer = float(kwargs.get("bbox_buffer_degrees", 0.25))
        params = {
            "bbox": f"{longitude - bbox_buffer},{latitude - bbox_buffer},{longitude + bbox_buffer},{latitude + bbox_buffer}",
            "limit": int(kwargs.get("station_limit", 25)),
            "f": "json",
        }
        if api_key:
            params["api_key"] = api_key

        try:
            locations_payload, location_meta = self._request_json(
                url="https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items",
                params=params,
                cache_context={"kind": "monitoring-locations", "bbox": params["bbox"]},
                cache_ttl_hours=24,
            )
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"USGS Water monitoring-location request failed: {exc}")

        features = locations_payload.get("features", [])
        if not features:
            return self._disabled_response(latitude, longitude, "USGS Water returned no nearby monitoring locations.")

        nearest = None
        nearest_distance = None
        for feature in features:
            coordinates = ((feature.get("geometry") or {}).get("coordinates") or [None, None])
            feature_lon, feature_lat = coordinates[0], coordinates[1]
            if feature_lat is None or feature_lon is None:
                continue
            distance = _miles_between(latitude, longitude, float(feature_lat), float(feature_lon))
            if nearest is None or distance < float(nearest_distance):
                nearest = feature
                nearest_distance = distance

        if nearest is None:
            return self._disabled_response(latitude, longitude, "USGS Water returned monitoring locations without usable coordinates.")

        monitoring_location_id = (nearest.get("properties") or {}).get("monitoring_location_id") or nearest.get("id")
        latest_params = {
            "monitoring_location_id": monitoring_location_id,
            "limit": int(kwargs.get("observation_limit", 20)),
            "f": "json",
        }
        if api_key:
            latest_params["api_key"] = api_key

        warnings: list[str] = []
        latest_features = []
        try:
            latest_payload, latest_meta = self._request_json(
                url="https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items",
                params=latest_params,
                cache_context={"kind": "latest-continuous", "monitoring_location_id": monitoring_location_id},
                cache_ttl_hours=0.5,
            )
            latest_features = latest_payload.get("features", [])
            if latest_meta.get("stale_cache"):
                warnings.append("Using stale cached USGS Water response because the live request failed.")
        except Exception as exc:
            warnings.append(f"USGS latest continuous values unavailable: {exc}")

        return self.normalize_response(
            {
                "nearest": nearest,
                "observations": latest_features,
                "distance_miles": round(float(nearest_distance), 2) if nearest_distance is not None else None,
                "location_cache_hit": location_meta.get("cache_hit", False),
            },
            latitude=latitude,
            longitude=longitude,
            warnings=warnings,
        )

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        warnings = list(kwargs.get("warnings", []))
        nearest = raw.get("nearest", {}) or {}
        nearest_props = nearest.get("properties", {}) or {}
        rows = []
        for feature in raw.get("observations", []):
            props = feature.get("properties", {}) or {}
            rows.append(
                {
                    "time": props.get("time"),
                    "parameter_code": props.get("parameter_code"),
                    "value": props.get("value"),
                    "unit_of_measure": props.get("unit_of_measure"),
                    "approvals_status": props.get("approvals_status"),
                }
            )

        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={
                "nearest_station": {
                    "monitoring_location_id": nearest_props.get("monitoring_location_id") or nearest.get("id"),
                    "monitoring_location_name": nearest_props.get("monitoring_location_name"),
                    "site_type": nearest_props.get("site_type"),
                    "state_name": nearest_props.get("state_name"),
                    "county_name": nearest_props.get("county_name"),
                    "distance_miles": raw.get("distance_miles"),
                },
                "latest_observations": rows,
            },
            units={"distance": "mi"},
            raw_metadata={"location_cache_hit": raw.get("location_cache_hit", False)},
            warnings=warnings,
        )
