from __future__ import annotations

from math import radians, sin, cos, sqrt, atan2
from typing import Any

from ranch_ai.data_sources.base import BaseDataSourceProvider


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_miles = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return earth_radius_miles * c


class TexMesonetDataSource(BaseDataSourceProvider):
    name = "texmesonet"
    category = "weather"
    requires_key = False
    access_level = "free_open_state"
    commercial_safe = True
    citation_url = "https://www.texmesonet.org/Apis"

    def fetch_point(self, latitude: float, longitude: float, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response(latitude, longitude, "TexMesonet is disabled in config/api_sources.yaml.")

        base_url = self.config.get("endpoint_url", "https://www.texmesonet.org")
        try:
            stations_payload, station_meta = self._request_json(
                url=f"{base_url}/api/Stations",
                cache_context={"kind": "stations"},
                cache_ttl_hours=12,
            )
            current_payload, current_meta = self._request_json(
                url=f"{base_url}/api/CurrentData",
                cache_context={"kind": "current"},
                cache_ttl_hours=0.5,
            )
        except Exception as exc:
            return self._disabled_response(latitude, longitude, f"TexMesonet request failed: {exc}")

        stations = stations_payload if isinstance(stations_payload, list) else stations_payload.get("data", [])
        current_rows = current_payload if isinstance(current_payload, list) else current_payload.get("data", [])
        if not stations:
            return self._disabled_response(latitude, longitude, "TexMesonet returned no station records.")

        nearest = None
        nearest_distance = None
        for station in stations:
            station_lat = station.get("Latitude") or station.get("latitude") or station.get("Lat")
            station_lon = station.get("Longitude") or station.get("longitude") or station.get("Lon")
            if station_lat is None or station_lon is None:
                continue
            distance = _distance_miles(latitude, longitude, float(station_lat), float(station_lon))
            if nearest is None or distance < float(nearest_distance):
                nearest = station
                nearest_distance = distance

        if nearest is None:
            return self._disabled_response(latitude, longitude, "TexMesonet station records did not include usable coordinates.")

        station_id = nearest.get("SiteId") or nearest.get("siteId") or nearest.get("StationId") or nearest.get("stationId")
        latest_row = next(
            (
                item
                for item in current_rows
                if str(item.get("SiteId") or item.get("siteId") or item.get("StationId") or item.get("stationId")) == str(station_id)
            ),
            {},
        )
        return self.normalize_response(
            {
                "nearest_station": nearest,
                "latest_row": latest_row,
                "station_cache_hit": station_meta.get("cache_hit", False),
                "current_cache_hit": current_meta.get("cache_hit", False),
                "distance_miles": round(float(nearest_distance), 2) if nearest_distance is not None else None,
            },
            latitude=latitude,
            longitude=longitude,
        )

    def normalize_response(self, raw: Any, **kwargs: Any) -> dict[str, Any]:
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        station = raw.get("nearest_station", {})
        latest = raw.get("latest_row", {})
        station_id = station.get("SiteId") or station.get("siteId") or station.get("StationId") or station.get("stationId")
        return self._response(
            latitude=latitude,
            longitude=longitude,
            data={
                "nearest_station": {
                    "station_id": station_id,
                    "station_name": station.get("SiteName") or station.get("siteName") or station.get("StationName") or station.get("stationName"),
                    "latitude": station.get("Latitude") or station.get("latitude"),
                    "longitude": station.get("Longitude") or station.get("longitude"),
                    "distance_miles": raw.get("distance_miles"),
                },
                "current": latest,
            },
            raw_metadata={
                "station_cache_hit": raw.get("station_cache_hit", False),
                "current_cache_hit": raw.get("current_cache_hit", False),
            },
            warnings=[],
        )
