import copy

import numpy as np
import pandas as pd
import pytest

from ranch_ai.api.vegetation_routes import post_vegetation_ndvi_history, post_vegetation_summary
from ranch_ai.config import settings
from ranch_ai.vegetation.cache import VegetationCache, hash_aoi_geometry
from ranch_ai.vegetation.ndvi_client import (
    EarthSearchSTACNDVIProvider,
    aggregate_ndvi_series,
    build_earth_search_query,
    calculate_ndvi_anomaly_metrics,
    calculate_ndvi_array,
    select_sentinel_2_assets,
)
from ranch_ai.vegetation.rap_client import RAPClient
from ranch_ai.vegetation.vegetation_scoring import calculate_trend_label, calculate_vegetation_health_score
from ranch_ai.vegetation.vegetation_service import VegetationService


TEXAS_AOI = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [-103.508361, 29.606667],
                [-103.511167, 29.606639],
                [-103.511139, 29.606000],
                [-103.508333, 29.606028],
                [-103.508361, 29.606667],
            ]
        ],
    },
    "properties": {"mask": True},
}


def _sample_rap_cover_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2021, 2022, 2023, 2024],
            "rap_annual_grass_forb_cover_pct": [10.0, 10.5, 11.0, 11.2],
            "rap_perennial_grass_forb_cover_pct": [33.0, 34.0, 35.0, 36.0],
            "rap_shrub_cover_pct": [8.0, 8.2, 8.5, 8.7],
            "rap_tree_cover_pct": [1.0, 1.0, 1.1, 1.1],
            "rap_litter_cover_pct": [12.0, 12.2, 12.5, 12.8],
            "rap_bare_ground_pct": [24.0, 23.0, 22.0, 21.0],
            "rap_total_vegetation_cover_pct": [64.0, 65.0, 66.0, 67.0],
        }
    )


def _sample_rap_production_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2021, 2022, 2023, 2024],
            "rap_annual_production_lb_ac": [140.0, 145.0, 150.0, 152.0],
            "rap_perennial_production_lb_ac": [410.0, 430.0, 445.0, 460.0],
            "rap_total_herbaceous_production_lb_ac": [550.0, 575.0, 595.0, 612.0],
        }
    )


def _sample_ndvi_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pasture_id": ["CC-001", "CC-001", "CC-001", "CC-001"],
            "date": pd.to_datetime(["2024-05-15", "2025-05-10", "2026-05-12", "2026-06-14"]),
            "ndvi_mean": [0.38, 0.44, 0.51, 0.48],
            "ndvi_min": [0.19, 0.23, 0.29, 0.25],
            "ndvi_max": [0.58, 0.63, 0.71, 0.68],
            "ndvi_std": [0.08, 0.07, 0.06, 0.07],
            "cloud_cover": [12.0, 10.0, 8.0, 15.0],
            "scene_id": ["S1", "S2", "S3", "S4"],
            "source": ["Earth Search STAC"] * 4,
            "sensor": ["sentinel-2-l2a"] * 4,
            "aggregation_mode": ["raw"] * 4,
        }
    )


def test_hash_aoi_geometry_is_stable_and_changes_with_shape():
    same_hash = hash_aoi_geometry(TEXAS_AOI)
    assert same_hash == hash_aoi_geometry(copy.deepcopy(TEXAS_AOI))

    shifted = copy.deepcopy(TEXAS_AOI)
    shifted["geometry"]["coordinates"][0][1][0] = -103.511000
    assert same_hash != hash_aoi_geometry(shifted)


def test_vegetation_cache_key_changes_with_context(tmp_path):
    cache = VegetationCache(tmp_path / "vegetation-cache", enabled=True)
    geometry_hash = hash_aoi_geometry(TEXAS_AOI)
    key_a = cache.build_cache_key(
        "Vegetation NDVI",
        "earth_search_stac",
        {
            "aoi_hash": geometry_hash,
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
            "params": {"sensor": "sentinel-2-l2a", "cloud_cover_max": 30, "aggregation_mode": "monthly_median"},
        },
    )
    key_b = cache.build_cache_key(
        "Vegetation NDVI",
        "earth_search_stac",
        {
            "aoi_hash": geometry_hash,
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
            "params": {"sensor": "sentinel-2-l2a", "cloud_cover_max": 20, "aggregation_mode": "monthly_median"},
        },
    )
    assert key_a != key_b


def test_parse_rap_cover_response():
    payload = {
        "type": "Feature",
        "properties": {
            "cover": [
                ["year", "AFG", "PFG", "SHR", "TRE", "LTR", "BGR"],
                [2022, 12.0, 33.5, 9.2, 1.0, 10.5, 20.8],
                [2023, 13.5, 31.0, 10.1, 1.2, 9.9, 22.3],
            ]
        },
    }

    frame = RAPClient.parse_cover_response(payload)
    assert list(frame["year"]) == [2022, 2023]
    assert "rap_perennial_grass_forb_cover_pct" in frame.columns
    assert round(float(frame["rap_total_vegetation_cover_pct"].iloc[0]), 1) == 66.2


def test_parse_rap_production_response():
    payload = {
        "type": "Feature",
        "properties": {
            "production": [
                ["year", "AFG", "PFG", "HER"],
                [2022, 145.0, 420.0, 565.0],
                [2023, 132.0, 401.0, 533.0],
            ]
        },
    }

    frame = RAPClient.parse_production_response(payload)
    assert list(frame["year"]) == [2022, 2023]
    assert float(frame["rap_total_herbaceous_production_lb_ac"].iloc[0]) == 565.0


def test_build_earth_search_query_includes_expected_filters():
    query = build_earth_search_query(
        TEXAS_AOI,
        start_date="2026-01-01",
        end_date="2026-03-31",
        collection="sentinel-2-l2a",
        cloud_cover_max=25,
        limit=120,
    )

    assert query["collections"] == ["sentinel-2-l2a"]
    assert query["limit"] == 120
    assert query["query"]["eo:cloud_cover"]["lte"] == 25.0
    assert query["intersects"]["type"] == "Polygon"
    assert query["datetime"].startswith("2026-01-01T00:00:00Z/")


def test_select_sentinel_2_assets_finds_red_and_nir():
    item = {
        "assets": {
            "B04": {"href": "https://example.com/red.tif"},
            "B08": {"href": "https://example.com/nir.tif"},
        }
    }

    assets = select_sentinel_2_assets(item)
    assert assets["red_key"] == "B04"
    assert assets["nir_key"] == "B08"


def test_select_sentinel_2_assets_raises_when_bands_missing():
    with pytest.raises(ValueError, match="missing usable Sentinel-2 Red/NIR assets"):
        select_sentinel_2_assets({"assets": {"visual": {"href": "https://example.com/visual.tif"}}})


def test_calculate_ndvi_array_uses_expected_formula_and_masks_zero_division():
    red = np.array([[0.2, 0.0]], dtype="float32")
    nir = np.array([[0.6, 0.0]], dtype="float32")

    ndvi = calculate_ndvi_array(red, nir)

    assert round(float(ndvi[0, 0]), 3) == 0.5
    assert bool(ndvi.mask[0, 1]) is True


def test_cloud_cover_filtering_respects_threshold():
    items = [
        {"id": "clear", "properties": {"eo:cloud_cover": 12}},
        {"id": "cloudy", "properties": {"eo:cloud_cover": 52}},
        {"id": "unknown", "properties": {}},
    ]

    filtered = EarthSearchSTACNDVIProvider._filter_items_by_cloud_cover(items, 30)
    assert [item["id"] for item in filtered] == ["clear", "unknown"]


def test_monthly_median_aggregation_reduces_scene_noise():
    frame = pd.DataFrame(
        {
            "pasture_id": ["CC-001", "CC-001", "CC-001"],
            "date": pd.to_datetime(["2026-05-01", "2026-05-15", "2026-06-01"]),
            "ndvi_mean": [0.30, 0.50, 0.60],
            "ndvi_min": [0.20, 0.40, 0.50],
            "ndvi_max": [0.40, 0.60, 0.70],
            "ndvi_std": [0.03, 0.05, 0.04],
            "cloud_cover": [10.0, 20.0, 12.0],
            "scene_id": ["M1", "M2", "J1"],
            "source": ["Earth Search STAC"] * 3,
            "sensor": ["sentinel-2-l2a"] * 3,
            "aggregation_mode": ["raw"] * 3,
        }
    )

    aggregated = aggregate_ndvi_series(frame, "monthly_median")
    assert len(aggregated) == 2
    assert round(float(aggregated["ndvi_mean"].iloc[0]), 2) == 0.40
    assert int(aggregated["scene_count"].iloc[0]) == 2
    assert aggregated["aggregation_mode"].iloc[0] == "monthly_median"


def test_ndvi_anomaly_calculation_returns_above_normal_when_latest_is_high():
    monthly = pd.DataFrame(
        {
            "pasture_id": ["CC-001", "CC-001", "CC-001"],
            "date": pd.to_datetime(["2024-05-01", "2025-05-01", "2026-05-01"]),
            "ndvi_mean": [0.40, 0.42, 0.50],
            "aggregation_mode": ["monthly_median"] * 3,
        }
    )

    metrics = calculate_ndvi_anomaly_metrics(monthly)
    assert metrics["status"] == "Above normal"
    assert metrics["anomaly_percent"] is not None and metrics["anomaly_percent"] > 10


def test_trend_and_scoring_model_handle_expected_patterns():
    label, slope = calculate_trend_label([20, 22, 24, 27, 29])
    assert label == "increasing"
    assert slope is not None and slope > 0

    cover_df = _sample_rap_cover_frame()
    production_df = _sample_rap_production_frame()

    score = calculate_vegetation_health_score(
        ndvi_latest=0.48,
        ndvi_historical_mean=0.41,
        ndvi_anomaly=0.07,
        ndvi_anomaly_percent=17.0,
        perennial_grass_trend="increasing",
        bare_ground_trend="declining",
        shrub_trend="stable",
        production_trend="increasing",
        rap_cover_series=cover_df,
        rap_production_series=production_df,
    )
    assert score.category in {"Excellent", "Good"}
    assert score.score is not None and score.score >= 70
    assert score.drivers


def test_invalid_geojson_is_rejected():
    runtime_settings = copy.deepcopy(settings)
    service = VegetationService(runtime_settings)

    with pytest.raises(ValueError, match="Polygon"):
        service.get_ndvi_history(
            {"type": "Point", "coordinates": [-103.5, 29.6]},
            start_date="2026-01-01",
            end_date="2026-02-01",
            aoi_id="CC-001",
            provider_name="mock",
        )


def test_ndvi_provider_failure_falls_back_to_mock_while_rap_succeeds(monkeypatch):
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "earth_search_stac"
    runtime_settings.public_data.cache_enabled = False
    service = VegetationService(runtime_settings)

    monkeypatch.setattr(
        "ranch_ai.vegetation.ndvi_client.EarthSearchSTACNDVIProvider.get_history",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("STAC timeout")),
    )
    monkeypatch.setattr(
        "ranch_ai.vegetation.rap_client.RAPClient.get_cover_meteorology_history",
        lambda self, feature: (_sample_rap_cover_frame(), {"provider": "rap"}),
    )
    monkeypatch.setattr(
        "ranch_ai.vegetation.rap_client.RAPClient.get_production_history",
        lambda self, feature: (_sample_rap_production_frame(), {"provider": "rap"}),
    )

    summary, ndvi_df, cover_df, production_df, _, details = service.get_vegetation_summary(
        TEXAS_AOI,
        aoi_id="CC-001",
        start_date="2025-01-01",
        end_date="2026-06-30",
        history_years=5,
    )

    assert not ndvi_df.empty
    assert not cover_df.empty
    assert not production_df.empty
    assert summary.ndvi_provider == "mock"
    assert summary.rap_provider == "rap"
    assert details["ndvi_status"]["mode"] == "fallback-mock"
    assert any("NDVI unavailable" in warning for warning in summary.warnings)


def test_rap_failure_falls_back_to_mock_while_ndvi_succeeds(monkeypatch):
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "earth_search_stac"
    runtime_settings.public_data.cache_enabled = False
    service = VegetationService(runtime_settings)

    monkeypatch.setattr(
        "ranch_ai.vegetation.ndvi_client.EarthSearchSTACNDVIProvider.get_history",
        lambda *args, **kwargs: (aggregate_ndvi_series(_sample_ndvi_frame(), "monthly_median"), {"provider": "earth_search_stac"}),
    )
    monkeypatch.setattr(
        "ranch_ai.vegetation.rap_client.RAPClient.get_cover_meteorology_history",
        lambda self, feature: (_ for _ in ()).throw(RuntimeError("RAP cover timeout")),
    )
    monkeypatch.setattr(
        "ranch_ai.vegetation.rap_client.RAPClient.get_production_history",
        lambda self, feature: (_ for _ in ()).throw(RuntimeError("RAP production timeout")),
    )

    summary, ndvi_df, cover_df, production_df, _, details = service.get_vegetation_summary(
        TEXAS_AOI,
        aoi_id="CC-001",
        start_date="2025-01-01",
        end_date="2026-06-30",
        history_years=5,
    )

    assert not ndvi_df.empty
    assert not cover_df.empty
    assert not production_df.empty
    assert summary.ndvi_provider == "earth_search_stac"
    assert summary.rap_provider == "mock"
    assert details["ndvi_status"]["mode"] == "real"
    assert details["rap_cover_status"]["mode"] == "fallback-mock"
    assert any("RAP cover history unavailable" in warning or "RAP production history unavailable" in warning for warning in summary.warnings)


def test_vegetation_service_summary_with_mock_provider():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "mock"

    service = VegetationService(runtime_settings)
    summary, ndvi_df, cover_df, production_df, _, _ = service.get_vegetation_summary(
        TEXAS_AOI,
        aoi_id="CC-001",
        start_date="2025-01-01",
        end_date="2026-03-01",
        history_years=5,
    )

    assert summary.ndvi["latest"] is not None
    assert summary.ndvi["aggregation_mode"] == "monthly_median"
    assert summary.rap["latest_year"] is not None
    assert not ndvi_df.empty
    assert not cover_df.empty
    assert not production_df.empty


def test_vegetation_summary_route_returns_sample_texas_polygon():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "mock"

    payload = {
        "aoi": TEXAS_AOI,
        "aoiId": "CC-001",
        "startDate": "2025-01-01",
        "endDate": "2026-03-01",
        "ndviProvider": "mock",
        "temporalAggregation": "monthly_median",
    }
    response = post_vegetation_summary(payload, app_settings=runtime_settings)

    assert response["aoi_id"] == "CC-001"
    assert response["ndvi"]["aggregation_mode"] == "monthly_median"
    assert "ndvi" in response and "rap" in response
    assert response["rangeiq_score"]["category"] in {"Excellent", "Good", "Watch", "Stressed", "Degraded", "Unknown"}


def test_ndvi_history_route_uses_monthly_median_mock_series():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "mock"

    payload = {
        "aoi": TEXAS_AOI,
        "aoiId": "CC-001",
        "startDate": "2025-01-01",
        "endDate": "2026-03-01",
        "ndviProvider": "mock",
        "temporalAggregation": "monthly_median",
    }
    response = post_vegetation_ndvi_history(payload, app_settings=runtime_settings)

    assert response["provider"] == "mock"
    assert response["mode"] == "mock"
    assert response["series"]
    assert response["series"][0]["aggregation_mode"] == "monthly_median"
