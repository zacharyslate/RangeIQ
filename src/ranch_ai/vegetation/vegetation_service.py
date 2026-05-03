from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.features.geospatial import polygon_area_acres
from ranch_ai.models.public_data_schema import PublicSourceStatus
from ranch_ai.vegetation.cache import VegetationCache, _normalize_geojson_input, hash_aoi_geometry
from ranch_ai.vegetation.mock_vegetation_provider import MockVegetationProvider
from ranch_ai.vegetation.ndvi_client import (
    AppEEARSNDVIProvider,
    ClimateEngineNDVIProvider,
    EarthSearchSTACNDVIProvider,
    MockNDVIProvider,
    annotate_ndvi_anomalies,
    calculate_ndvi_anomaly_metrics,
)
from ranch_ai.vegetation.rap_client import RAP_API_DOCS_URL, RAPClient
from ranch_ai.vegetation.vegetation_scoring import calculate_trend_label, calculate_vegetation_health_score, ndvi_status_label, trend_score_value
from ranch_ai.vegetation.vegetation_types import VegetationArtifacts, VegetationSummary


def _coerce_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


class VegetationService:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings
        self.cache = VegetationCache(
            cache_dir=self.settings.vegetation_cache_dir,
            enabled=self.settings.public_data.cache_enabled,
        )
        self.mock_provider = MockVegetationProvider(seed=self.settings.random_seed)

    def _mock_ndvi_history(
        self,
        aoi_feature: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float,
        sensor: str,
        temporal_aggregation: str,
    ) -> pd.DataFrame:
        frame, _ = MockNDVIProvider(seed=self.settings.random_seed).get_history(
            aoi_feature,
            aoi_id=aoi_id,
            start_date=start_date,
            end_date=end_date,
            cloud_cover_max=cloud_cover_max,
            sensor=sensor,
            temporal_aggregation=temporal_aggregation,
        )
        return frame

    def _ndvi_provider(self, provider_name: str):
        config = self.settings.public_data.vegetation
        if provider_name == "earth_search_stac":
            return EarthSearchSTACNDVIProvider(
                stac_url=config.earth_search_stac_url,
                default_collection=config.ndvi_default_collection,
                default_cloud_cover_max=config.ndvi_cloud_cover_max,
                default_limit=config.earth_search_max_items,
                timeout_seconds=config.timeout_seconds,
            )
        if provider_name == "climate_engine":
            return ClimateEngineNDVIProvider(
                api_key_env=config.climate_engine_api_key_env,
                base_url=config.climate_engine_base_url,
                dataset=config.climate_engine_dataset,
                variable=config.climate_engine_variable,
                area_reducer=config.climate_engine_area_reducer,
                timeout_seconds=config.timeout_seconds,
            )
        if provider_name == "appeears":
            return AppEEARSNDVIProvider(
                username_env=config.appeears_username_env,
                password_env=config.appeears_password_env,
                timeout_seconds=config.timeout_seconds,
            )
        return MockNDVIProvider(seed=self.settings.random_seed)

    def _validate_aoi(self, aoi_geojson: dict[str, Any], *, aoi_id: str, acres_hint: float | None = None) -> tuple[dict[str, Any], float]:
        feature = _normalize_geojson_input(aoi_geojson)
        polygon = feature["geometry"]["coordinates"][0]
        acres = float(acres_hint) if acres_hint is not None else float(polygon_area_acres(polygon))
        if acres > float(self.settings.public_data.vegetation.max_aoi_acres):
            raise ValueError(
                f"{aoi_id} is too large for this MVP vegetation request ({acres:,.0f} acres). "
                f"Limit is {self.settings.public_data.vegetation.max_aoi_acres:,.0f} acres."
            )
        return feature, acres

    @staticmethod
    def _build_aoi_feature(pasture_row: pd.Series) -> dict[str, Any]:
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [pasture_row["geometry"]]},
            "properties": {
                "pasture_id": pasture_row["pasture_id"],
                "name": pasture_row["name"],
            },
        }

    def _cache_context(
        self,
        *,
        aoi_feature: dict[str, Any],
        aoi_id: str,
        endpoint: str,
        provider_name: str,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = {
            "aoi_id": aoi_id,
            "aoi_hash": hash_aoi_geometry(aoi_feature),
            "endpoint": endpoint,
            "provider": provider_name,
        }
        if start_date is not None:
            context["start_date"] = _coerce_timestamp(start_date).strftime("%Y-%m-%d")
        if end_date is not None:
            context["end_date"] = _coerce_timestamp(end_date).strftime("%Y-%m-%d")
        if extra:
            context["params"] = extra
        return context

    @staticmethod
    def _serialize_frame(frame: pd.DataFrame, *, date_columns: list[str] | None = None) -> dict[str, Any]:
        serialized = frame.copy()
        for column in date_columns or []:
            if column in serialized.columns:
                serialized[column] = pd.to_datetime(serialized[column]).dt.strftime("%Y-%m-%d")
        return {"records": serialized.to_dict(orient="records")}

    @staticmethod
    def _deserialize_frame(payload: dict[str, Any], *, date_columns: list[str] | None = None) -> pd.DataFrame:
        frame = pd.DataFrame(payload.get("records", []))
        for column in date_columns or []:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column])
        return frame

    def get_ndvi_history(
        self,
        aoi_geojson: dict[str, Any],
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        *,
        aoi_id: str,
        provider_name: str | None = None,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        provider_name = (provider_name or self.settings.public_data.vegetation.provider).lower()
        feature, _ = self._validate_aoi(aoi_geojson, aoi_id=aoi_id)
        active_cloud_cover = float(cloud_cover_max if cloud_cover_max is not None else self.settings.public_data.vegetation.ndvi_cloud_cover_max)
        active_sensor = sensor or self.settings.public_data.vegetation.ndvi_default_collection
        active_aggregation = temporal_aggregation or self.settings.public_data.vegetation.ndvi_temporal_aggregation
        recognized_providers = {"mock", "earth_search_stac", "climate_engine", "appeears"}
        if provider_name not in recognized_providers:
            frame = self._mock_ndvi_history(
                feature,
                aoi_id=aoi_id,
                start_date=start_date,
                end_date=end_date,
                cloud_cover_max=active_cloud_cover,
                sensor=active_sensor,
                temporal_aggregation=active_aggregation,
            )
            return frame, {"provider": "mock"}, {
                "provider": "mock",
                "mode": "fallback-mock",
                "warnings": [f"{provider_name} NDVI provider is not supported; using mock NDVI history instead."],
            }

        provider = self._ndvi_provider(provider_name)
        context_params = {
            "sensor": active_sensor,
            "cloud_cover_max": active_cloud_cover,
            "aggregation_mode": active_aggregation,
        }
        if provider_name == "climate_engine":
            context_params.update(
                {
                    "dataset": self.settings.public_data.vegetation.climate_engine_dataset,
                    "variable": self.settings.public_data.vegetation.climate_engine_variable,
                }
            )

        context = self._cache_context(
            aoi_feature=feature,
            aoi_id=aoi_id,
            endpoint="ndvi-history",
            provider_name=provider_name,
            start_date=start_date,
            end_date=end_date,
            extra=context_params,
        )

        if provider_name == "mock":
            frame, raw = provider.get_history(
                feature,
                aoi_id=aoi_id,
                start_date=start_date,
                end_date=end_date,
                cloud_cover_max=active_cloud_cover,
                sensor=active_sensor,
                temporal_aggregation=active_aggregation,
            )
            return frame, raw, {"provider": "mock", "mode": "mock", "warnings": []}

        cached = self.cache.load("Vegetation NDVI", provider_name, context)
        if cached is not None and cached.is_fresh:
            frame = self._deserialize_frame(cached.normalized_payload, date_columns=["date"])
            return frame, cached.raw_payload or {}, {"provider": provider_name, "mode": "cached", "warnings": []}

        try:
            frame, raw = provider.get_history(
                feature,
                aoi_id=aoi_id,
                start_date=start_date,
                end_date=end_date,
                cloud_cover_max=active_cloud_cover,
                sensor=active_sensor,
                temporal_aggregation=active_aggregation,
            )
            self.cache.save(
                component="Vegetation NDVI",
                provider_name=provider_name,
                context=context,
                normalized_payload=self._serialize_frame(frame, date_columns=["date"]),
                raw_payload=raw,
                refresh_hours=float(self.settings.public_data.vegetation.cache_ttl_days) * 24.0,
            )
            return frame, raw, {"provider": provider_name, "mode": "real", "warnings": []}
        except Exception as exc:
            if cached is not None:
                frame = self._deserialize_frame(cached.normalized_payload, date_columns=["date"])
                return frame, cached.raw_payload or {}, {
                    "provider": provider_name,
                    "mode": "stale-cache",
                    "warnings": [f"{provider_name} NDVI refresh failed; using cached data instead. {exc}"],
                }
            frame = self._mock_ndvi_history(
                feature,
                aoi_id=aoi_id,
                start_date=start_date,
                end_date=end_date,
                cloud_cover_max=active_cloud_cover,
                sensor=active_sensor,
                temporal_aggregation=active_aggregation,
            )
            return frame, {"provider": "mock"}, {
                "provider": "mock",
                "mode": "fallback-mock",
                "warnings": [f"{provider_name} NDVI unavailable; using mock NDVI history instead. {exc}"],
            }

    def _load_rap_component(
        self,
        *,
        aoi_geojson: dict[str, Any],
        aoi_id: str,
        endpoint_name: str,
        fetcher: Any,
        date_columns: list[str] | None = None,
        refresh_hours: int | float | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        feature, _ = self._validate_aoi(aoi_geojson, aoi_id=aoi_id)
        context = self._cache_context(
            aoi_feature=feature,
            aoi_id=aoi_id,
            endpoint=endpoint_name,
            provider_name="rap",
        )

        cached = self.cache.load("Vegetation RAP", "rap", context)
        if cached is not None and cached.is_fresh:
            frame = self._deserialize_frame(cached.normalized_payload, date_columns=date_columns)
            return frame, cached.raw_payload or {}, {"provider": "rap", "mode": "cached", "warnings": []}

        try:
            frame, raw = fetcher(feature)
            self.cache.save(
                component="Vegetation RAP",
                provider_name="rap",
                context=context,
                normalized_payload=self._serialize_frame(frame, date_columns=date_columns),
                raw_payload=raw,
                refresh_hours=refresh_hours,
            )
            return frame, raw, {"provider": "rap", "mode": "real", "warnings": []}
        except Exception as exc:
            if cached is not None:
                frame = self._deserialize_frame(cached.normalized_payload, date_columns=date_columns)
                return frame, cached.raw_payload or {}, {
                    "provider": "rap",
                    "mode": "stale-cache",
                    "warnings": [f"RAP {endpoint_name} refresh failed; using cached data instead. {exc}"],
                }
            raise RuntimeError(str(exc))

    def get_rap_cover_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        include_meteorology: bool = False,
    ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        if self.settings.public_data.vegetation.provider.lower() == "mock":
            end_year = pd.Timestamp.now().year - 1
            start_year = max(1986, end_year - self.settings.default_history_years + 1)
            frame = self.mock_provider.get_rap_cover_history(aoi_id, start_year, end_year)
            return frame, {"provider": "mock"}, {"provider": "mock", "mode": "mock", "warnings": []}

        client = RAPClient(
            timeout_seconds=self.settings.public_data.vegetation.timeout_seconds,
            cover_url=self.settings.public_data.vegetation.rap_cover_url,
            cover_meteorology_url=self.settings.public_data.vegetation.rap_cover_meteorology_url,
            production_url=self.settings.public_data.vegetation.rap_production_url,
            production_16day_url=self.settings.public_data.vegetation.rap_production_16day_url,
        )
        endpoint_name = "coverMeteorologyV3" if include_meteorology else "coverV3"
        try:
            frame, raw, status = self._load_rap_component(
                aoi_geojson=aoi_geojson,
                aoi_id=aoi_id,
                endpoint_name=endpoint_name,
                fetcher=(lambda feature: client.get_cover_meteorology_history(feature)) if include_meteorology else (lambda feature: client.get_cover_history(feature)),
                refresh_hours=self.settings.public_data.vegetation.rap_refresh_hours,
            )
            frame["pasture_id"] = aoi_id
            return frame, raw, status
        except Exception as exc:
            end_year = pd.Timestamp.now().year - 1
            start_year = max(1986, end_year - self.settings.default_history_years + 1)
            frame = self.mock_provider.get_rap_cover_history(aoi_id, start_year, end_year)
            return frame, {"provider": "mock"}, {
                "provider": "mock",
                "mode": "fallback-mock",
                "warnings": [f"RAP cover history unavailable; using mock RAP cover history instead. {exc}"],
            }

    def get_rap_production_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        include_16day: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
        if self.settings.public_data.vegetation.provider.lower() == "mock":
            end_year = pd.Timestamp.now().year - 1
            start_year = max(1986, end_year - self.settings.default_history_years + 1)
            frame = self.mock_provider.get_rap_production_history(aoi_id, start_year, end_year)
            interval_frame = self.mock_provider.get_rap_production_16day_history(aoi_id, max(end_year - 1, start_year), end_year) if include_16day else pd.DataFrame()
            return frame, interval_frame, {"provider": "mock", "mode": "mock", "warnings": []}, {"provider": "mock", "mode": "mock", "warnings": []}

        client = RAPClient(
            timeout_seconds=self.settings.public_data.vegetation.timeout_seconds,
            cover_url=self.settings.public_data.vegetation.rap_cover_url,
            cover_meteorology_url=self.settings.public_data.vegetation.rap_cover_meteorology_url,
            production_url=self.settings.public_data.vegetation.rap_production_url,
            production_16day_url=self.settings.public_data.vegetation.rap_production_16day_url,
        )
        try:
            frame, raw, status = self._load_rap_component(
                aoi_geojson=aoi_geojson,
                aoi_id=aoi_id,
                endpoint_name="productionV3",
                fetcher=lambda feature: client.get_production_history(feature),
                refresh_hours=self.settings.public_data.vegetation.rap_refresh_hours,
            )
            frame["pasture_id"] = aoi_id

            interval_frame = pd.DataFrame()
            interval_status = {"provider": "rap", "mode": status["mode"], "warnings": []}
            if include_16day:
                interval_frame, _, interval_status = self._load_rap_component(
                    aoi_geojson=aoi_geojson,
                    aoi_id=aoi_id,
                    endpoint_name="production16dayV3",
                    fetcher=lambda feature: client.get_production_16day_history(feature),
                    date_columns=["date"],
                    refresh_hours=self.settings.public_data.vegetation.rap_refresh_hours,
                )
                interval_frame["pasture_id"] = aoi_id
            return frame, interval_frame, status, interval_status
        except Exception as exc:
            end_year = pd.Timestamp.now().year - 1
            start_year = max(1986, end_year - self.settings.default_history_years + 1)
            frame = self.mock_provider.get_rap_production_history(aoi_id, start_year, end_year)
            interval_frame = self.mock_provider.get_rap_production_16day_history(aoi_id, max(end_year - 1, start_year), end_year) if include_16day else pd.DataFrame()
            status = {
                "provider": "mock",
                "mode": "fallback-mock",
                "warnings": [f"RAP production history unavailable; using mock RAP production history instead. {exc}"],
            }
            interval_status = {
                "provider": "mock",
                "mode": "fallback-mock" if include_16day else "mock",
                "warnings": [],
            }
            return frame, interval_frame, status, interval_status

    @staticmethod
    def _prepare_ndvi_summary(ndvi_series: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
        if ndvi_series.empty:
            return {
                "latest": None,
                "historical_mean": None,
                "anomaly": None,
                "anomaly_percent": None,
                "status": "Unknown",
                "trend": "unknown",
                "aggregation_mode": "monthly_median",
                "source_label": "Unavailable",
                "series": [],
            }, ndvi_series

        monthly = annotate_ndvi_anomalies(ndvi_series.copy())
        monthly["date"] = pd.to_datetime(monthly["date"])
        monthly["month_start"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
        anomaly_metrics = calculate_ndvi_anomaly_metrics(monthly)
        latest = monthly.sort_values("date").iloc[-1]
        trend_label, _ = calculate_trend_label(monthly["ndvi_mean"])
        aggregation_mode = str(latest.get("aggregation_mode") or "monthly_median")
        sensor = str(latest.get("sensor") or "sentinel-2-l2a")
        source_name = str(latest.get("source") or "NDVI provider")
        if "earth search" in source_name.lower() or "sentinel" in sensor.lower():
            source_label = "Earth Search STAC / Sentinel-2"
        elif "climate engine" in source_name.lower():
            source_label = "Climate Engine"
        elif "appeears" in source_name.lower():
            source_label = "AppEEARS (Legacy)"
        elif "mock" in source_name.lower() or sensor.lower() == "mock":
            source_label = "Mock vegetation history"
        else:
            source_label = source_name
        summary = {
            "latest": anomaly_metrics["latest"],
            "historical_mean": anomaly_metrics["historical_mean"],
            "anomaly": anomaly_metrics["anomaly"],
            "anomaly_percent": anomaly_metrics["anomaly_percent"],
            "status": ndvi_status_label(anomaly_metrics["anomaly_percent"]),
            "trend": trend_label,
            "aggregation_mode": aggregation_mode,
            "source_label": source_label,
            "series": [
                {
                    "date": pd.Timestamp(record.date).strftime("%Y-%m-%d"),
                    "ndvi_mean": round(float(record.ndvi_mean), 3),
                    "historical_mean": round(float(record.historical_mean), 3) if pd.notna(record.historical_mean) else None,
                    "ndvi_anomaly": round(float(record.ndvi_anomaly), 3) if pd.notna(record.ndvi_anomaly) else None,
                    "ndvi_anomaly_percent": round(float(record.ndvi_anomaly_percent), 1) if pd.notna(record.ndvi_anomaly_percent) else None,
                    "status": str(record.anomaly_status),
                    "ndvi_min": round(float(record.ndvi_min), 3) if pd.notna(record.ndvi_min) else None,
                    "ndvi_max": round(float(record.ndvi_max), 3) if pd.notna(record.ndvi_max) else None,
                    "ndvi_std": round(float(record.ndvi_std), 3) if pd.notna(record.ndvi_std) else None,
                    "cloud_cover": round(float(record.cloud_cover), 2) if pd.notna(record.cloud_cover) else None,
                    "scene_count": int(record.scene_count) if hasattr(record, "scene_count") and pd.notna(record.scene_count) else None,
                    "source": str(getattr(record, "source", "NDVI provider")),
                    "sensor": str(getattr(record, "sensor", sensor)),
                    "aggregation_mode": aggregation_mode,
                }
                for record in monthly.sort_values("date").itertuples(index=False)
            ],
        }
        return summary, monthly

    @staticmethod
    def _prepare_rap_summary(rap_cover_series: pd.DataFrame, rap_production_series: pd.DataFrame) -> dict[str, Any]:
        perennial_trend, perennial_slope = calculate_trend_label(rap_cover_series.get("rap_perennial_grass_forb_cover_pct", pd.Series(dtype=float)))
        bare_ground_trend, bare_slope = calculate_trend_label(rap_cover_series.get("rap_bare_ground_pct", pd.Series(dtype=float)))
        shrub_trend, shrub_slope = calculate_trend_label(rap_cover_series.get("rap_shrub_cover_pct", pd.Series(dtype=float)))
        production_trend, production_slope = calculate_trend_label(rap_production_series.get("rap_total_herbaceous_production_lb_ac", pd.Series(dtype=float)))
        latest_year = int(rap_cover_series["year"].max()) if not rap_cover_series.empty else (int(rap_production_series["year"].max()) if not rap_production_series.empty else None)
        return {
            "latest_year": latest_year,
            "perennial_grass_trend": perennial_trend,
            "bare_ground_trend": bare_ground_trend,
            "shrub_trend": shrub_trend,
            "production_trend": production_trend,
            "perennial_grass_trend_score": perennial_slope,
            "bare_ground_trend_score": bare_slope,
            "shrub_trend_score": shrub_slope,
            "production_trend_score": production_slope,
            "cover_series": [
                {
                    "year": int(record.year),
                    "annual_grass_forb_cover_pct": round(float(record.rap_annual_grass_forb_cover_pct), 3),
                    "perennial_grass_forb_cover_pct": round(float(record.rap_perennial_grass_forb_cover_pct), 3),
                    "shrub_cover_pct": round(float(record.rap_shrub_cover_pct), 3),
                    "tree_cover_pct": round(float(record.rap_tree_cover_pct), 3),
                    "bare_ground_pct": round(float(record.rap_bare_ground_pct), 3),
                    "litter_cover_pct": round(float(record.rap_litter_cover_pct), 3),
                    "total_vegetation_cover_pct": round(float(record.rap_total_vegetation_cover_pct), 3),
                }
                for record in rap_cover_series.sort_values("year").itertuples(index=False)
            ],
            "production_series": [
                {
                    "year": int(record.year),
                    "annual_production_lb_ac": round(float(record.rap_annual_production_lb_ac), 3),
                    "perennial_production_lb_ac": round(float(record.rap_perennial_production_lb_ac), 3),
                    "total_herbaceous_production_lb_ac": round(float(record.rap_total_herbaceous_production_lb_ac), 3),
                }
                for record in rap_production_series.sort_values("year").itertuples(index=False)
            ],
        }

    @staticmethod
    def _monthly_public_features(
        *,
        pasture_id: str,
        month_frame: pd.DataFrame,
        rap_cover_series: pd.DataFrame,
        rap_production_series: pd.DataFrame,
        rap_summary: dict[str, Any],
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        month_index = pd.date_range(
            start=pd.Timestamp(start_date).to_period("M").to_timestamp(),
            end=pd.Timestamp(end_date).to_period("M").to_timestamp(),
            freq="MS",
        )
        if month_frame.empty:
            month_features = pd.DataFrame({"pasture_id": pasture_id, "month_start": month_index})
        else:
            month_features = month_frame.loc[month_frame["month_start"].isin(month_index)].copy()
            month_features = month_features.rename(
                columns={
                    "ndvi_mean": "public_ndvi_mean",
                    "historical_mean": "public_ndvi_historical_mean",
                    "ndvi_anomaly": "public_ndvi_anomaly",
                }
            )
            month_features = month_features[["pasture_id", "month_start", "public_ndvi_mean", "public_ndvi_historical_mean", "public_ndvi_anomaly"]]

        if month_features.empty:
            month_features = pd.DataFrame({"pasture_id": pasture_id, "month_start": month_index})

        rap_cover = rap_cover_series.copy()
        rap_cover["feature_year"] = rap_cover["year"].astype(int)
        rap_prod = rap_production_series.copy()
        rap_prod["feature_year"] = rap_prod["year"].astype(int)

        rows: list[dict[str, Any]] = []
        for month_start in month_index:
            year = month_start.year
            cover_slice = rap_cover.loc[rap_cover["feature_year"] <= year].sort_values("feature_year")
            prod_slice = rap_prod.loc[rap_prod["feature_year"] <= year].sort_values("feature_year")
            latest_cover = cover_slice.iloc[-1] if not cover_slice.empty else None
            latest_prod = prod_slice.iloc[-1] if not prod_slice.empty else None
            rows.append(
                {
                    "pasture_id": pasture_id,
                    "month_start": pd.Timestamp(month_start),
                    "public_fractional_cover": (
                        round(float(latest_cover["rap_total_vegetation_cover_pct"]) / 100.0, 3) if latest_cover is not None else None
                    ),
                    "public_rap_annual_grass_cover_pct": float(latest_cover["rap_annual_grass_forb_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_perennial_grass_cover_pct": float(latest_cover["rap_perennial_grass_forb_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_shrub_cover_pct": float(latest_cover["rap_shrub_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_tree_cover_pct": float(latest_cover["rap_tree_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_bare_ground_pct": float(latest_cover["rap_bare_ground_pct"]) if latest_cover is not None else None,
                    "public_rap_litter_cover_pct": float(latest_cover["rap_litter_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_total_vegetation_cover_pct": float(latest_cover["rap_total_vegetation_cover_pct"]) if latest_cover is not None else None,
                    "public_rap_herbaceous_production_lb_ac": float(latest_prod["rap_total_herbaceous_production_lb_ac"]) if latest_prod is not None else None,
                    "public_rap_annual_production_lb_ac": float(latest_prod["rap_annual_production_lb_ac"]) if latest_prod is not None else None,
                    "public_rap_perennial_production_lb_ac": float(latest_prod["rap_perennial_production_lb_ac"]) if latest_prod is not None else None,
                    "public_rap_perennial_trend_score": trend_score_value(rap_summary["perennial_grass_trend"]),
                    "public_rap_bare_ground_trend_score": trend_score_value(rap_summary["bare_ground_trend"]),
                    "public_rap_shrub_trend_score": trend_score_value(rap_summary["shrub_trend"]),
                    "public_rap_production_trend_score": trend_score_value(rap_summary["production_trend"]),
                }
            )

        rap_monthly = pd.DataFrame(rows)
        return month_features.merge(rap_monthly, on=["pasture_id", "month_start"], how="left").sort_values("month_start").reset_index(drop=True)

    def get_vegetation_summary(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        ndvi_provider: str | None = None,
        history_years: int | None = None,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str | None = None,
        include_raw: bool = False,
    ) -> tuple[VegetationSummary, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        history_years = int(history_years or self.settings.default_history_years)
        end_timestamp = _coerce_timestamp(end_date)
        ndvi_start = max(_coerce_timestamp(start_date) - pd.DateOffset(years=history_years), pd.Timestamp("1986-01-01"))
        cover_df, cover_raw, cover_status = self.get_rap_cover_history(aoi_geojson, aoi_id=aoi_id, include_meteorology=True)
        production_df, production_16day_df, production_status, production_16day_status = self.get_rap_production_history(
            aoi_geojson,
            aoi_id=aoi_id,
            include_16day=False,
        )
        ndvi_df, ndvi_raw, ndvi_status = self.get_ndvi_history(
            aoi_geojson,
            ndvi_start,
            end_timestamp,
            aoi_id=aoi_id,
            provider_name=ndvi_provider,
            cloud_cover_max=cloud_cover_max,
            sensor=sensor,
            temporal_aggregation=temporal_aggregation,
        )

        warnings = ndvi_status["warnings"] + cover_status["warnings"] + production_status["warnings"] + production_16day_status["warnings"]
        ndvi_summary, monthly_ndvi = self._prepare_ndvi_summary(ndvi_df)
        rap_summary = self._prepare_rap_summary(cover_df, production_df)
        score = calculate_vegetation_health_score(
            ndvi_latest=ndvi_summary["latest"],
            ndvi_historical_mean=ndvi_summary["historical_mean"],
            ndvi_anomaly=ndvi_summary["anomaly"],
            ndvi_anomaly_percent=ndvi_summary["anomaly_percent"],
            perennial_grass_trend=rap_summary["perennial_grass_trend"],
            bare_ground_trend=rap_summary["bare_ground_trend"],
            shrub_trend=rap_summary["shrub_trend"],
            production_trend=rap_summary["production_trend"],
            rap_cover_series=cover_df,
            rap_production_series=production_df,
        )
        summary = VegetationSummary(
            aoi_id=aoi_id,
            date_range={
                "start": pd.Timestamp(ndvi_start).strftime("%Y-%m-%d"),
                "end": pd.Timestamp(end_timestamp).strftime("%Y-%m-%d"),
            },
            ndvi=ndvi_summary,
            rap=rap_summary,
            rangeiq_score=score.to_dict(),
            ndvi_provider=ndvi_status["provider"],
            rap_provider=cover_status["provider"],
            warnings=warnings,
        )
        details = {
            "ndvi_status": ndvi_status,
            "rap_cover_status": cover_status,
            "rap_production_status": production_status,
            "rap_production_16day_status": production_16day_status,
        }
        if include_raw:
            details["raw"] = {
                "ndvi": ndvi_raw,
                "rap_cover": cover_raw,
                "rap_production": production_df.to_dict(orient="records"),
            }
        return summary, monthly_ndvi, cover_df, production_df, production_16day_df, details

    def build_artifacts(
        self,
        pastures: pd.DataFrame,
        *,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        history_years: int | None = None,
    ) -> tuple[VegetationArtifacts, list[PublicSourceStatus]]:
        loaded_at = pd.Timestamp.now()
        monthly_frames: list[pd.DataFrame] = []
        ndvi_series_frames: list[pd.DataFrame] = []
        rap_cover_frames: list[pd.DataFrame] = []
        rap_production_frames: list[pd.DataFrame] = []
        rap_16day_frames: list[pd.DataFrame] = []
        summary_rows: list[dict[str, Any]] = []
        summaries: list[VegetationSummary] = []
        warnings: list[str] = []
        ndvi_modes: list[str] = []
        rap_modes: list[str] = []
        ndvi_active_providers: list[str] = []
        rap_active_providers: list[str] = []
        ndvi_warnings: list[str] = []
        rap_warnings: list[str] = []

        for pasture in pastures.itertuples(index=False):
            aoi = self._build_aoi_feature(pd.Series(pasture._asdict()))
            summary, ndvi_monthly, cover_df, production_df, production_16day_df, details = self.get_vegetation_summary(
                aoi,
                aoi_id=str(pasture.pasture_id),
                start_date=start_date,
                end_date=end_date,
                ndvi_provider=self.settings.public_data.vegetation.provider,
                history_years=history_years,
            )
            summaries.append(summary)
            warnings.extend(summary.warnings)

            ndvi_status = details["ndvi_status"]
            rap_cover_status = details["rap_cover_status"]
            rap_production_status = details["rap_production_status"]
            ndvi_modes.append(ndvi_status["mode"])
            rap_modes.append(rap_cover_status["mode"] if rap_cover_status["mode"] != "real" else rap_production_status["mode"])
            ndvi_active_providers.append(ndvi_status["provider"])
            rap_active_providers.append(rap_cover_status["provider"])
            ndvi_warnings.extend(ndvi_status.get("warnings", []))
            rap_warnings.extend(rap_cover_status.get("warnings", []))
            rap_warnings.extend(rap_production_status.get("warnings", []))

            monthly_features = self._monthly_public_features(
                pasture_id=str(pasture.pasture_id),
                month_frame=ndvi_monthly.assign(pasture_id=str(pasture.pasture_id)),
                rap_cover_series=cover_df.assign(pasture_id=str(pasture.pasture_id)),
                rap_production_series=production_df.assign(pasture_id=str(pasture.pasture_id)),
                rap_summary=summary.rap,
                start_date=start_date,
                end_date=end_date,
            )
            monthly_frames.append(monthly_features)

            ndvi_series_frames.append(ndvi_monthly.assign(pasture_id=str(pasture.pasture_id)))
            rap_cover_frames.append(cover_df.assign(pasture_id=str(pasture.pasture_id)))
            rap_production_frames.append(production_df.assign(pasture_id=str(pasture.pasture_id)))
            if not production_16day_df.empty:
                rap_16day_frames.append(production_16day_df.assign(pasture_id=str(pasture.pasture_id)))

            summary_rows.append(
                {
                    "pasture_id": str(pasture.pasture_id),
                    "name": str(pasture.name),
                    "ndvi_latest": summary.ndvi["latest"],
                    "ndvi_historical_mean": summary.ndvi["historical_mean"],
                    "ndvi_anomaly": summary.ndvi["anomaly"],
                    "ndvi_anomaly_percent": summary.ndvi["anomaly_percent"],
                    "ndvi_status": summary.ndvi["status"],
                    "ndvi_trend": summary.ndvi["trend"],
                    "ndvi_source_label": summary.ndvi["source_label"],
                    "ndvi_aggregation_mode": summary.ndvi["aggregation_mode"],
                    "rap_latest_year": summary.rap["latest_year"],
                    "rap_perennial_grass_trend": summary.rap["perennial_grass_trend"],
                    "rap_bare_ground_trend": summary.rap["bare_ground_trend"],
                    "rap_shrub_trend": summary.rap["shrub_trend"],
                    "rap_production_trend": summary.rap["production_trend"],
                    "rangeiq_vegetation_score": summary.rangeiq_score["score"],
                    "rangeiq_vegetation_category": summary.rangeiq_score["category"],
                    "rangeiq_vegetation_explanation": summary.rangeiq_score["explanation"],
                    "rangeiq_vegetation_drivers": " | ".join(summary.rangeiq_score["drivers"]),
                    "vegetation_warnings": " | ".join(summary.warnings),
                }
            )

        artifacts = VegetationArtifacts(
            monthly_features=pd.concat(monthly_frames, ignore_index=True) if monthly_frames else pd.DataFrame(),
            ndvi_series=pd.concat(ndvi_series_frames, ignore_index=True) if ndvi_series_frames else pd.DataFrame(),
            rap_cover_series=pd.concat(rap_cover_frames, ignore_index=True) if rap_cover_frames else pd.DataFrame(),
            rap_production_series=pd.concat(rap_production_frames, ignore_index=True) if rap_production_frames else pd.DataFrame(),
            rap_production_16day_series=pd.concat(rap_16day_frames, ignore_index=True) if rap_16day_frames else pd.DataFrame(),
            summary_frame=pd.DataFrame(summary_rows),
            summaries=summaries,
            warnings=warnings,
        )

        ndvi_mode = "real"
        if all(mode == "cached" for mode in ndvi_modes):
            ndvi_mode = "cached"
        elif any("fallback" in mode for mode in ndvi_modes):
            ndvi_mode = "fallback-mock"
        elif all(mode == "mock" for mode in ndvi_modes):
            ndvi_mode = "mock"

        rap_mode = "real"
        if all(mode == "cached" for mode in rap_modes):
            rap_mode = "cached"
        elif any("fallback" in mode for mode in rap_modes):
            rap_mode = "fallback-mock"
        elif all(mode == "mock" for mode in rap_modes):
            rap_mode = "mock"

        statuses = [
            PublicSourceStatus(
                component="Vegetation NDVI",
                configured_provider=self.settings.public_data.vegetation.provider,
                active_provider=ndvi_active_providers[0] if ndvi_active_providers else "mock",
                mode=ndvi_mode,
                status=(
                    f"Using {ndvi_active_providers[0]} NDVI history for {len(summaries)} pasture(s)."
                    if not ndvi_warnings
                    else ndvi_warnings[0]
                ),
                citation_url=(
                    self.settings.public_data.vegetation.earth_search_stac_url
                    if (ndvi_active_providers and ndvi_active_providers[0] == "earth_search_stac")
                    else "https://docs.climateengine.org/docs/build/html/timeseries.html"
                    if (ndvi_active_providers and ndvi_active_providers[0] == "climate_engine")
                    else "https://appeears.earthdatacloud.nasa.gov/api/"
                    if (ndvi_active_providers and ndvi_active_providers[0] == "appeears")
                    else "synthetic NDVI history"
                ),
                loaded_at=loaded_at,
            ),
            PublicSourceStatus(
                component="Vegetation RAP",
                configured_provider="rap",
                active_provider=rap_active_providers[0] if rap_active_providers else "mock",
                mode=rap_mode,
                status=(
                    f"Using RAP rangeland history for {len(summaries)} pasture(s)."
                    if rap_mode in {"real", "cached"}
                    else rap_warnings[0] if rap_warnings else "Using mock RAP rangeland history."
                ),
                citation_url=RAP_API_DOCS_URL,
                loaded_at=loaded_at,
            ),
        ]
        return artifacts, statuses

    @staticmethod
    def summary_as_dict(summary: VegetationSummary) -> dict[str, Any]:
        return summary.to_dict()
