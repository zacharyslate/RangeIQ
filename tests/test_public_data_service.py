import copy

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.data.public_sources import (
    NasaPowerHistoricalWeatherProvider,
    USDASoilDataAccessProvider,
    USDroughtMonitorProvider,
)
from ranch_ai.pipeline import build_synthetic_dataset, run_mvp_pipeline
from ranch_ai.services.public_data_service import PublicDataService


def test_public_data_service_returns_mock_bundle():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.historical_weather.provider = "mock"
    runtime_settings.public_data.soils.provider = "mock"
    runtime_settings.public_data.drought.provider = "mock"
    runtime_settings.public_data.vegetation.provider = "mock"

    pastures, weekly_data, _, _ = build_synthetic_dataset(weeks=8, seed=42)
    bundle = PublicDataService(runtime_settings).load_public_data_bundle(
        pastures=pastures,
        start_date=weekly_data["week_start"].min(),
        end_date=weekly_data["week_start"].max(),
    )

    assert len(bundle.source_status) == 5
    assert not bundle.historical_weather.empty
    assert not bundle.soils.empty
    assert not bundle.drought.empty
    assert not bundle.vegetation.empty
    assert bundle.vegetation_artifacts is not None


def test_unsupported_vegetation_provider_falls_back_to_mock():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data.vegetation.provider = "legacy_login_provider"

    pastures, weekly_data, _, _ = build_synthetic_dataset(weeks=6, seed=42)
    bundle = PublicDataService(runtime_settings).load_public_data_bundle(
        pastures=pastures,
        start_date=weekly_data["week_start"].min(),
        end_date=weekly_data["week_start"].max(),
    )

    vegetation_status = next(status for status in bundle.source_status if status.component == "Vegetation NDVI")
    assert vegetation_status.configured_provider == "legacy_login_provider"
    assert vegetation_status.active_provider == "mock"
    assert vegetation_status.mode == "fallback-mock"
    assert "not supported" in vegetation_status.status


def test_nasa_power_provider_normalizes_response(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "properties": {
                    "parameter": {
                        "T2M": {"20260101": 20.0, "20260102": 21.0},
                        "T2M_MAX": {"20260101": 27.0, "20260102": 28.0},
                        "T2M_MIN": {"20260101": 14.0, "20260102": 15.0},
                        "PRECTOTCORR": {"20260101": 5.0, "20260102": 0.0},
                        "RH2M": {"20260101": 32.0, "20260102": 35.0},
                        "WS2M": {"20260101": 4.0, "20260102": 5.0},
                    }
                }
            }

    def fake_get(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr("ranch_ai.data.public_sources.requests.get", fake_get)

    provider = NasaPowerHistoricalWeatherProvider(timeout_seconds=5)
    history = provider.get_daily_history(29.606333, -103.50975, "2026-01-01", "2026-01-02")

    assert len(history) == 2
    assert {"date", "public_temp_mean_f", "public_precip_in", "public_wind_speed_mph"}.issubset(history.columns)
    assert float(history["public_temp_mean_f"].iloc[0]) > 60
    assert float(history["public_precip_in"].iloc[0]) > 0


def test_usda_sda_provider_normalizes_response(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Table": [
                    ["mukey", "muname", "compname", "drainagecl", "aws0100wta"],
                    ["123456", "Mock mapunit", "Brewster loam", "Well drained", "18.4"],
                ]
            }

    def fake_post(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr("ranch_ai.data.public_sources.requests.post", fake_post)

    pastures, _, _, _ = build_synthetic_dataset(weeks=4, seed=42)
    provider = USDASoilDataAccessProvider(timeout_seconds=5)
    frame = provider.get_pasture_soils(pastures)

    assert not frame.empty
    assert {"public_soil_type", "public_available_water_capacity_in", "public_soil_drainage_class"}.issubset(frame.columns)
    assert frame["public_soil_type"].iloc[0] == "Brewster loam"


def test_usdm_provider_normalizes_response(monkeypatch):
    class CensusResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "geographies": {
                        "Counties": [
                            {
                                "GEOID": "48043",
                                "NAME": "Brewster County",
                            }
                        ]
                    }
                }
            }

    class UsdmResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"MapDate": "2026-01-06", "None": 30, "D0": 20, "D1": 50, "D2": 0, "D3": 0, "D4": 0},
                {"MapDate": "2026-01-13", "None": 10, "D0": 15, "D1": 25, "D2": 50, "D3": 0, "D4": 0},
            ]

    def fake_get(url, *args, **kwargs):
        if "geocoding.geo.census.gov" in url:
            return CensusResponse()
        if "usdmdataservices.unl.edu" in url:
            return UsdmResponse()
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("ranch_ai.data.public_sources.requests.get", fake_get)

    provider = USDroughtMonitorProvider(timeout_seconds=5)
    frame = provider.get_weekly_drought(29.606333, -103.50975, "2026-01-01", "2026-01-20")

    assert len(frame) == 2
    assert {
        "public_usdm_category",
        "public_usdm_score",
        "public_usdm_drought_coverage_pct",
        "public_usdm_max_intensity_pct",
        "public_usdm_county_fips",
    }.issubset(frame.columns)
    assert frame["public_usdm_county_fips"].iloc[0] == "48043"
    assert frame["public_usdm_category"].iloc[0] == "D1"
    assert frame["public_usdm_category"].iloc[1] == "D2"


def test_public_data_service_reuses_cached_history(tmp_path, monkeypatch):
    call_count = {"count": 0}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "properties": {
                    "parameter": {
                        "T2M": {"20260101": 20.0, "20260102": 21.0},
                        "T2M_MAX": {"20260101": 27.0, "20260102": 28.0},
                        "T2M_MIN": {"20260101": 14.0, "20260102": 15.0},
                        "PRECTOTCORR": {"20260101": 5.0, "20260102": 0.0},
                        "RH2M": {"20260101": 32.0, "20260102": 35.0},
                        "WS2M": {"20260101": 4.0, "20260102": 5.0},
                    }
                }
            }

    def fake_get(*args, **kwargs):
        call_count["count"] += 1
        return DummyResponse()

    monkeypatch.setattr("ranch_ai.data.public_sources.requests.get", fake_get)

    runtime_settings = copy.deepcopy(settings)
    runtime_settings.public_data_cache_dir = tmp_path / "public-cache"
    runtime_settings.public_data.cache_enabled = True
    runtime_settings.public_data.historical_weather.provider = "nasa_power"
    runtime_settings.public_data.historical_weather.refresh_hours = 168
    runtime_settings.public_data.soils.provider = "mock"
    runtime_settings.public_data.drought.provider = "mock"
    runtime_settings.public_data.vegetation.provider = "mock"

    pastures, weekly_data, _, _ = build_synthetic_dataset(weeks=8, seed=42)
    service = PublicDataService(runtime_settings)
    bundle_1 = service.load_public_data_bundle(
        pastures=pastures,
        start_date=weekly_data["week_start"].min(),
        end_date=weekly_data["week_start"].max(),
    )
    bundle_2 = service.load_public_data_bundle(
        pastures=pastures,
        start_date=weekly_data["week_start"].min(),
        end_date=weekly_data["week_start"].max(),
    )

    assert call_count["count"] == 1
    assert bundle_1.source_status[0].mode == "real"
    assert bundle_2.source_status[0].mode == "cached"
    assert not bundle_2.historical_weather.empty
    assert bundle_2.source_status[0].cache_path is not None


def test_training_dataset_includes_public_feature_columns():
    artifacts = run_mvp_pipeline(weeks=10, seed=11, write_outputs=False)

    assert artifacts.training_dataset_summary["public_feature_count"] > 0
    assert {
        "public_temp_mean_7d_f",
        "public_usdm_score",
        "public_usdm_drought_coverage_pct",
        "public_available_water_capacity_in",
        "public_ndvi_mean",
        "public_fractional_cover",
        "public_rap_perennial_grass_cover_pct",
        "public_rap_herbaceous_production_lb_ac",
    }.issubset(artifacts.weekly_data.columns)
