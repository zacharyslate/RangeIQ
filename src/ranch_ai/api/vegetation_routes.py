from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.vegetation.vegetation_service import VegetationService


def _require_aoi(payload: dict[str, Any]) -> dict[str, Any]:
    aoi = payload.get("aoi")
    if not isinstance(aoi, dict):
        raise ValueError("Vegetation API requests require an 'aoi' GeoJSON payload.")
    return aoi


def post_vegetation_summary(payload: dict[str, Any], app_settings: Settings = settings) -> dict[str, Any]:
    service = VegetationService(app_settings)
    aoi = _require_aoi(payload)
    start_date = payload.get("startDate") or payload.get("start_date") or pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    end_date = payload.get("endDate") or payload.get("end_date") or pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    ndvi_provider = payload.get("ndviProvider")
    cloud_cover_max = payload.get("cloudCoverMax")
    sensor = payload.get("sensor")
    temporal_aggregation = payload.get("temporalAggregation")
    include_raw = bool(payload.get("includeRaw", False))
    summary, ndvi_series, rap_cover, rap_production, rap_16day, details = service.get_vegetation_summary(
        aoi,
        aoi_id=str(payload.get("aoiId") or payload.get("aoi_id") or "AOI-001"),
        start_date=start_date,
        end_date=end_date,
        ndvi_provider=ndvi_provider,
        history_years=payload.get("historyYears"),
        cloud_cover_max=cloud_cover_max,
        sensor=sensor,
        temporal_aggregation=temporal_aggregation,
        include_raw=include_raw,
    )
    result = summary.to_dict()
    result["ndvi"]["series"] = summary.ndvi["series"]
    result["rap"]["cover_series"] = summary.rap["cover_series"]
    result["rap"]["production_series"] = summary.rap["production_series"]
    result["warnings"] = summary.warnings
    if include_raw:
        result["raw"] = details.get("raw", {})
    result["tables"] = {
        "ndvi": ndvi_series.to_dict(orient="records"),
        "rap_cover": rap_cover.to_dict(orient="records"),
        "rap_production": rap_production.to_dict(orient="records"),
        "rap_production_16day": rap_16day.to_dict(orient="records"),
    }
    return result


def post_vegetation_rap_history(payload: dict[str, Any], app_settings: Settings = settings) -> dict[str, Any]:
    service = VegetationService(app_settings)
    aoi = _require_aoi(payload)
    aoi_id = str(payload.get("aoiId") or payload.get("aoi_id") or "AOI-001")
    cover_df, _, cover_status = service.get_rap_cover_history(aoi, aoi_id=aoi_id, include_meteorology=True)
    production_df, production_16day_df, production_status, _ = service.get_rap_production_history(
        aoi,
        aoi_id=aoi_id,
        include_16day=bool(payload.get("include16Day", False)),
    )
    return {
        "aoi_id": aoi_id,
        "cover": cover_df.to_dict(orient="records"),
        "production": production_df.to_dict(orient="records"),
        "production16day": production_16day_df.to_dict(orient="records"),
        "cover_status": cover_status,
        "production_status": production_status,
    }


def post_vegetation_ndvi_history(payload: dict[str, Any], app_settings: Settings = settings) -> dict[str, Any]:
    service = VegetationService(app_settings)
    aoi = _require_aoi(payload)
    aoi_id = str(payload.get("aoiId") or payload.get("aoi_id") or "AOI-001")
    start_date = payload.get("startDate") or payload.get("start_date")
    end_date = payload.get("endDate") or payload.get("end_date")
    provider_name = payload.get("ndviProvider")
    cloud_cover_max = payload.get("cloudCoverMax")
    sensor = payload.get("sensor")
    temporal_aggregation = payload.get("temporalAggregation")
    frame, _, status = service.get_ndvi_history(
        aoi,
        start_date=start_date,
        end_date=end_date,
        aoi_id=aoi_id,
        provider_name=provider_name,
        cloud_cover_max=cloud_cover_max,
        sensor=sensor,
        temporal_aggregation=temporal_aggregation,
    )
    return {
        "aoi_id": aoi_id,
        "provider": status["provider"],
        "mode": status["mode"],
        "warnings": status["warnings"],
        "series": frame.to_dict(orient="records"),
    }


def post_vegetation_score(payload: dict[str, Any], app_settings: Settings = settings) -> dict[str, Any]:
    summary = post_vegetation_summary(payload, app_settings=app_settings)
    return summary["rangeiq_score"]


def dispatch_vegetation_route(
    path: str,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    app_settings: Settings = settings,
) -> dict[str, Any]:
    if method.upper() != "POST":
        raise ValueError("RangeIQ vegetation routes currently support POST only for GeoJSON AOIs.")

    route_map = {
        "/api/vegetation/summary": post_vegetation_summary,
        "/api/vegetation/rap/history": post_vegetation_rap_history,
        "/api/vegetation/ndvi/history": post_vegetation_ndvi_history,
        "/api/vegetation/score": post_vegetation_score,
    }
    if path not in route_map:
        raise ValueError(f"Unknown vegetation route: {path}")
    return route_map[path](payload, app_settings=app_settings)
