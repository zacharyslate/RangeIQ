from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
import time
from typing import Any

import numpy as np
import pandas as pd
import requests

from ranch_ai.vegetation.cache import _normalize_geojson_input
from ranch_ai.vegetation.mock_vegetation_provider import generate_mock_ndvi_history


EARTH_SEARCH_STAC_URL = "https://earth-search.aws.element84.com/v1"
EARTH_SEARCH_DOCS_URL = "https://element84.com/earth-search/"
CLIMATE_ENGINE_DOCS_URL = "https://docs.climateengine.org/docs/build/html/timeseries.html"
CLIMATE_ENGINE_AUTH_URL = "https://docs.climateengine.org/docs/build/html/authentication.html"
CLIMATE_ENGINE_REGISTRATION_URL = "https://docs.climateengine.org/docs/build/html/registration.html"
APPEEARS_DOCS_URL = "https://appeears.earthdatacloud.nasa.gov/api/"


class NDVIProvider(ABC):
    provider_name = "base"
    citation_url = ""

    @abstractmethod
    def get_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str = "raw",
    ) -> tuple[pd.DataFrame, Any]:
        raise NotImplementedError


def _coerce_record_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                records.append(item)
            elif isinstance(item, list):
                for nested in item:
                    if isinstance(nested, dict):
                        records.append(nested)
        return records
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                nested_records = _coerce_record_list(value)
                if nested_records:
                    return nested_records
    return []


def parse_climate_engine_ndvi_response(payload: Any, aoi_id: str) -> pd.DataFrame:
    records = _coerce_record_list(payload)
    if not records:
        raise ValueError("Climate Engine returned no NDVI records for this AOI.")

    rows: list[dict[str, object]] = []
    for record in records:
        lowered = {str(key).lower(): value for key, value in record.items()}
        raw_date = lowered.get("date") or lowered.get("datetime") or lowered.get("time")
        ndvi_value = lowered.get("ndvi")
        if raw_date is None or ndvi_value in {None, "", -9999, -9999.0}:
            continue
        ndvi_std = lowered.get("ndvi_std") or lowered.get("stdev") or lowered.get("std")
        rows.append(
            {
                "pasture_id": aoi_id,
                "date": pd.to_datetime(raw_date),
                "ndvi_mean": pd.to_numeric(ndvi_value, errors="coerce"),
                "ndvi_min": pd.to_numeric(lowered.get("ndvi_min") or lowered.get("min"), errors="coerce"),
                "ndvi_max": pd.to_numeric(lowered.get("ndvi_max") or lowered.get("max"), errors="coerce"),
                "ndvi_std": pd.to_numeric(ndvi_std, errors="coerce"),
                "cloud_cover": pd.to_numeric(lowered.get("cloud_cover") or lowered.get("eo:cloud_cover"), errors="coerce"),
                "scene_id": str(lowered.get("scene_id") or lowered.get("id") or pd.to_datetime(raw_date).strftime("%Y-%m-%d")),
                "source": "Climate Engine NDVI",
                "sensor": "Climate Engine",
                "aggregation_mode": "raw",
            }
        )

    frame = pd.DataFrame(rows).dropna(subset=["date", "ndvi_mean"]).sort_values("date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("Climate Engine returned NDVI records, but none contained usable NDVI values.")
    return frame


def build_earth_search_query(
    aoi_geojson: dict[str, Any],
    *,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    collection: str = "sentinel-2-l2a",
    cloud_cover_max: float = 30.0,
    limit: int = 240,
) -> dict[str, Any]:
    feature = _normalize_geojson_input(aoi_geojson)
    return {
        "collections": [collection],
        "datetime": f"{pd.Timestamp(start_date).strftime('%Y-%m-%dT00:00:00Z')}/{pd.Timestamp(end_date).strftime('%Y-%m-%dT23:59:59Z')}",
        "intersects": feature["geometry"],
        "limit": int(limit),
        "query": {"eo:cloud_cover": {"lte": float(cloud_cover_max)}},
    }


def select_sentinel_2_assets(item: dict[str, Any]) -> dict[str, Any]:
    assets = item.get("assets", {})
    if not isinstance(assets, dict) or not assets:
        raise ValueError("STAC item did not include any assets.")

    def _usable_asset(asset_key: str) -> bool:
        asset = assets.get(asset_key, {})
        href = str(asset.get("href", "")).strip()
        return bool(href) and "jp2" not in asset_key.lower()

    for red_key, nir_key in [("red", "nir"), ("B04", "B08")]:
        if _usable_asset(red_key) and _usable_asset(nir_key):
            return {
                "red_key": red_key,
                "nir_key": nir_key,
                "red_asset": assets[red_key],
                "nir_asset": assets[nir_key],
            }

    red_asset = None
    nir_asset = None
    red_key = None
    nir_key = None
    for asset_key, asset in assets.items():
        if "jp2" in asset_key.lower():
            continue
        bands = asset.get("eo:bands", [])
        common_names = {str(band.get("common_name", "")).lower() for band in bands if isinstance(band, dict)}
        names = {str(band.get("name", "")).upper() for band in bands if isinstance(band, dict)}
        if red_asset is None and ("red" in common_names or "B04" in names):
            red_asset = asset
            red_key = asset_key
        if nir_asset is None and ("nir" in common_names or "B08" in names):
            nir_asset = asset
            nir_key = asset_key

    if red_asset is None or nir_asset is None:
        raise ValueError("STAC item is missing usable Sentinel-2 Red/NIR assets.")

    return {
        "red_key": red_key,
        "nir_key": nir_key,
        "red_asset": red_asset,
        "nir_asset": nir_asset,
    }


def calculate_ndvi_array(red: Any, nir: Any) -> np.ma.MaskedArray:
    red_array = np.ma.asarray(red, dtype="float32")
    nir_array = np.ma.asarray(nir, dtype="float32")
    red_data = np.asarray(red_array.filled(np.nan), dtype="float32")
    nir_data = np.asarray(nir_array.filled(np.nan), dtype="float32")
    mask = np.ma.getmaskarray(red_array) | np.ma.getmaskarray(nir_array)
    denominator = nir_data + red_data
    invalid = ~np.isfinite(red_data) | ~np.isfinite(nir_data) | ~np.isfinite(denominator) | (denominator == 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir_data - red_data) / denominator
    mask = mask | invalid | ~np.isfinite(ndvi)
    return np.ma.array(ndvi, mask=mask)


def annotate_ndvi_anomalies(series: pd.DataFrame) -> pd.DataFrame:
    if series.empty or "date" not in series.columns or "ndvi_mean" not in series.columns:
        return series.copy()

    frame = series.copy().sort_values("date").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["historical_mean"] = np.nan
    frame["ndvi_anomaly"] = np.nan
    frame["ndvi_anomaly_percent"] = np.nan
    frame["anomaly_status"] = "Unknown"

    aggregation_mode = str(frame.get("aggregation_mode", pd.Series(["raw"])).iloc[-1]).lower()
    if aggregation_mode == "seasonal_mean" and "season" not in frame.columns:
        frame["season"] = frame["date"].dt.month.map(
            {
                12: "DJF",
                1: "DJF",
                2: "DJF",
                3: "MAM",
                4: "MAM",
                5: "MAM",
                6: "JJA",
                7: "JJA",
                8: "JJA",
                9: "SON",
                10: "SON",
                11: "SON",
            }
        )

    for index, row in frame.iterrows():
        if aggregation_mode == "seasonal_mean" and "season" in frame.columns:
            period_match = frame["season"] == row.get("season")
        else:
            period_match = frame["date"].dt.month == row["date"].month
        prior_values = pd.to_numeric(frame.loc[(frame.index < index) & period_match, "ndvi_mean"], errors="coerce").dropna()
        if len(prior_values) < 2:
            continue
        historical_mean = float(prior_values.mean())
        anomaly = float(row["ndvi_mean"] - historical_mean)
        anomaly_percent = None if historical_mean == 0 else float((anomaly / abs(historical_mean)) * 100.0)
        frame.at[index, "historical_mean"] = historical_mean
        frame.at[index, "ndvi_anomaly"] = anomaly
        if anomaly_percent is not None:
            frame.at[index, "ndvi_anomaly_percent"] = anomaly_percent
        frame.at[index, "anomaly_status"] = (
            "Above normal"
            if anomaly_percent is not None and anomaly_percent > 10
            else "Below normal"
            if anomaly_percent is not None and anomaly_percent < -10
            else "Normal"
            if anomaly_percent is not None
            else "Unknown"
        )
    return frame


def aggregate_ndvi_series(series: pd.DataFrame, mode: str = "raw") -> pd.DataFrame:
    if series.empty:
        return series.copy()

    normalized_mode = str(mode or "raw").lower()
    frame = series.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").reset_index(drop=True)

    if normalized_mode == "raw":
        if "scene_count" not in frame.columns:
            frame["scene_count"] = 1
        frame["aggregation_mode"] = "raw"
        return frame

    if normalized_mode in {"monthly_mean", "monthly_median"}:
        frame["month_start"] = frame["date"].dt.to_period("M").dt.to_timestamp()
        ndvi_agg = "mean" if normalized_mode == "monthly_mean" else "median"
        cloud_agg = "mean" if normalized_mode == "monthly_mean" else "median"
        aggregated = (
            frame.groupby(["pasture_id", "month_start"], as_index=False)
            .agg(
                ndvi_mean=("ndvi_mean", ndvi_agg),
                ndvi_min=("ndvi_min", "min"),
                ndvi_max=("ndvi_max", "max"),
                ndvi_std=("ndvi_std", ndvi_agg),
                cloud_cover=("cloud_cover", cloud_agg),
                scene_count=("scene_id", "count"),
                source=("source", "last"),
                sensor=("sensor", "last"),
            )
            .rename(columns={"month_start": "date"})
        )
        aggregated["aggregation_mode"] = normalized_mode
        return aggregated.sort_values("date").reset_index(drop=True)

    if normalized_mode == "seasonal_mean":
        frame["season"] = frame["date"].dt.month.map(
            {
                12: "DJF",
                1: "DJF",
                2: "DJF",
                3: "MAM",
                4: "MAM",
                5: "MAM",
                6: "JJA",
                7: "JJA",
                8: "JJA",
                9: "SON",
                10: "SON",
                11: "SON",
            }
        )
        frame["season_year"] = frame["date"].dt.year
        frame.loc[frame["date"].dt.month == 12, "season_year"] = frame.loc[frame["date"].dt.month == 12, "season_year"] + 1
        aggregated = (
            frame.groupby(["pasture_id", "season_year", "season"], as_index=False)
            .agg(
                ndvi_mean=("ndvi_mean", "mean"),
                ndvi_min=("ndvi_min", "min"),
                ndvi_max=("ndvi_max", "max"),
                ndvi_std=("ndvi_std", "mean"),
                cloud_cover=("cloud_cover", "mean"),
                scene_count=("scene_id", "count"),
                source=("source", "last"),
                sensor=("sensor", "last"),
            )
        )
        season_start_map = {"DJF": "-12-01", "MAM": "-03-01", "JJA": "-06-01", "SON": "-09-01"}
        aggregated["date"] = [
            pd.Timestamp(f"{int(record.season_year - 1 if record.season == 'DJF' else record.season_year)}{season_start_map[record.season]}")
            for record in aggregated.itertuples(index=False)
        ]
        aggregated["aggregation_mode"] = normalized_mode
        return aggregated.sort_values("date").reset_index(drop=True)

    raise ValueError(f"Unsupported NDVI aggregation mode: {mode}")


def calculate_ndvi_anomaly_metrics(series: pd.DataFrame) -> dict[str, Any]:
    annotated = annotate_ndvi_anomalies(series)
    if annotated.empty or "date" not in annotated.columns or "ndvi_mean" not in annotated.columns:
        return {
            "latest": None,
            "historical_mean": None,
            "anomaly": None,
            "anomaly_percent": None,
            "status": "Unknown",
        }

    latest = annotated.iloc[-1]
    latest_ndvi = pd.to_numeric(latest.get("ndvi_mean"), errors="coerce")
    if pd.isna(latest_ndvi):
        return {
            "latest": None,
            "historical_mean": None,
            "anomaly": None,
            "anomaly_percent": None,
            "status": "Unknown",
        }

    historical_mean = pd.to_numeric(latest.get("historical_mean"), errors="coerce")
    anomaly = pd.to_numeric(latest.get("ndvi_anomaly"), errors="coerce")
    anomaly_percent = pd.to_numeric(latest.get("ndvi_anomaly_percent"), errors="coerce")
    if pd.isna(historical_mean):
        return {
            "latest": round(float(latest_ndvi), 3),
            "historical_mean": None,
            "anomaly": None,
            "anomaly_percent": None,
            "status": "Unknown",
        }

    status = str(latest.get("anomaly_status") or "Unknown")
    return {
        "latest": round(float(latest_ndvi), 3),
        "historical_mean": round(float(historical_mean), 3),
        "anomaly": round(float(anomaly), 3) if not pd.isna(anomaly) else None,
        "anomaly_percent": round(float(anomaly_percent), 1) if not pd.isna(anomaly_percent) else None,
        "status": status,
    }


class MockNDVIProvider(NDVIProvider):
    provider_name = "mock"
    citation_url = "synthetic NDVI history"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str = "raw",
    ) -> tuple[pd.DataFrame, Any]:
        frame = generate_mock_ndvi_history(aoi_id, start_date, end_date, seed=self.seed)
        frame["cloud_cover"] = np.nan
        frame["scene_id"] = frame["date"].dt.strftime("%Y-%m")
        frame["sensor"] = sensor or "mock"
        frame["aggregation_mode"] = "raw"
        return aggregate_ndvi_series(frame, temporal_aggregation), {"provider": "mock"}


class EarthSearchSTACNDVIProvider(NDVIProvider):
    provider_name = "earth_search_stac"
    citation_url = EARTH_SEARCH_DOCS_URL

    def __init__(
        self,
        *,
        stac_url: str = EARTH_SEARCH_STAC_URL,
        default_collection: str = "sentinel-2-l2a",
        default_cloud_cover_max: float = 30.0,
        default_limit: int = 240,
        timeout_seconds: int = 20,
        retries: int = 2,
        backoff_seconds: float = 0.5,
    ):
        self.stac_url = stac_url.rstrip("/")
        self.default_collection = default_collection
        self.default_cloud_cover_max = float(default_cloud_cover_max)
        self.default_limit = int(default_limit)
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()

    @staticmethod
    def raster_dependencies_available() -> bool:
        try:
            import rasterio  # noqa: F401
            from rasterio.mask import mask  # noqa: F401
            from rasterio.warp import transform_geom  # noqa: F401
        except ImportError:
            return False
        return True

    def _search_items(self, query: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    f"{self.stac_url}/search",
                    json=query,
                    headers={"Accept": "application/geo+json"},
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError(f"Earth Search STAC request failed: {last_exc}")

    @staticmethod
    def _filter_items_by_cloud_cover(items: list[dict[str, Any]], cloud_cover_max: float) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for item in items:
            cloud_cover = pd.to_numeric(item.get("properties", {}).get("eo:cloud_cover"), errors="coerce")
            if pd.isna(cloud_cover) or float(cloud_cover) <= float(cloud_cover_max):
                filtered.append(item)
        return filtered

    @staticmethod
    def _asset_scale_offset(asset: dict[str, Any]) -> tuple[float, float]:
        bands = asset.get("raster:bands", [])
        if isinstance(bands, list) and bands:
            band = bands[0]
            scale = float(band.get("scale", 1.0) or 1.0)
            offset = float(band.get("offset", 0.0) or 0.0)
            return scale, offset
        return 1.0, 0.0

    def _scene_ndvi_stats(
        self,
        item: dict[str, Any],
        geometry: dict[str, Any],
        *,
        red_asset: dict[str, Any],
        nir_asset: dict[str, Any],
    ) -> dict[str, float]:
        try:
            import rasterio
            from rasterio.mask import mask
            from rasterio.warp import transform_geom
        except ImportError as exc:  # pragma: no cover - exercised by provider fallback path
            raise RuntimeError("earth_search_stac NDVI requires rasterio to read Sentinel-2 assets.") from exc

        red_href = str(red_asset.get("href", "")).strip()
        nir_href = str(nir_asset.get("href", "")).strip()
        if not red_href or not nir_href:
            raise ValueError("Sentinel-2 STAC item did not include usable Red/NIR asset URLs.")

        with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open(red_href) as red_ds, rasterio.open(nir_href) as nir_ds:
                geometry_projected = transform_geom("EPSG:4326", red_ds.crs, geometry, precision=6)
                red_data, _ = mask(red_ds, [geometry_projected], crop=True, filled=False)
                nir_data, _ = mask(nir_ds, [geometry_projected], crop=True, filled=False)

        red_scale, red_offset = self._asset_scale_offset(red_asset)
        nir_scale, nir_offset = self._asset_scale_offset(nir_asset)
        red_band = np.ma.asarray(red_data[0], dtype="float32") * red_scale + red_offset
        nir_band = np.ma.asarray(nir_data[0], dtype="float32") * nir_scale + nir_offset
        ndvi = calculate_ndvi_array(red_band, nir_band)
        values = np.asarray(ndvi.compressed(), dtype="float32")
        if values.size == 0:
            raise ValueError("AOI did not produce any valid NDVI pixels for this scene.")

        return {
            "ndvi_mean": round(float(values.mean()), 4),
            "ndvi_min": round(float(values.min()), 4),
            "ndvi_max": round(float(values.max()), 4),
            "ndvi_std": round(float(values.std(ddof=0)), 4),
        }

    def get_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str = "raw",
    ) -> tuple[pd.DataFrame, Any]:
        if not self.raster_dependencies_available():
            raise RuntimeError("earth_search_stac NDVI requires rasterio. Reinstall RangeIQ to enable the live STAC NDVI provider.")

        collection = sensor or self.default_collection
        if collection != "sentinel-2-l2a":
            raise NotImplementedError(
                f"Earth Search NDVI currently supports sentinel-2-l2a only. Requested collection: {collection}"
            )

        cloud_limit = float(cloud_cover_max if cloud_cover_max is not None else self.default_cloud_cover_max)
        feature = _normalize_geojson_input(aoi_geojson)
        query = build_earth_search_query(
            feature,
            start_date=start_date,
            end_date=end_date,
            collection=collection,
            cloud_cover_max=cloud_limit,
            limit=self.default_limit,
        )
        payload = self._search_items(query)
        items = payload.get("features", [])
        if not items:
            raise ValueError("Earth Search STAC returned no scenes for this AOI and date range.")

        filtered_items = self._filter_items_by_cloud_cover(items, cloud_limit)
        if not filtered_items:
            raise ValueError("Earth Search STAC returned scenes, but all were above the allowed cloud-cover threshold.")

        rows: list[dict[str, object]] = []
        warnings: list[str] = []
        for item in filtered_items:
            try:
                asset_info = select_sentinel_2_assets(item)
                stats = self._scene_ndvi_stats(
                    item,
                    feature["geometry"],
                    red_asset=asset_info["red_asset"],
                    nir_asset=asset_info["nir_asset"],
                )
                rows.append(
                    {
                        "pasture_id": aoi_id,
                        "date": pd.to_datetime(item.get("properties", {}).get("datetime") or item.get("datetime")),
                        "ndvi_mean": stats["ndvi_mean"],
                        "ndvi_min": stats["ndvi_min"],
                        "ndvi_max": stats["ndvi_max"],
                        "ndvi_std": stats["ndvi_std"],
                        "cloud_cover": pd.to_numeric(item.get("properties", {}).get("eo:cloud_cover"), errors="coerce"),
                        "scene_id": item.get("id"),
                        "source": "Earth Search STAC",
                        "sensor": "sentinel-2-l2a",
                        "aggregation_mode": "raw",
                    }
                )
            except Exception as exc:
                warnings.append(f"{item.get('id', 'scene')}: {exc}")

        frame = pd.DataFrame(rows).dropna(subset=["date", "ndvi_mean"]).sort_values("date").reset_index(drop=True)
        if frame.empty:
            raise ValueError(
                "Earth Search STAC found scenes, but none produced usable NDVI values. "
                + (" ".join(warnings[:3]) if warnings else "")
            )

        aggregated = aggregate_ndvi_series(frame, temporal_aggregation)
        raw_metadata = {
            "query": query,
            "items_returned": len(items),
            "items_used": len(frame),
            "item_ids": [str(item.get("id")) for item in filtered_items],
            "warnings": warnings,
            "provider": self.provider_name,
            "sensor": collection,
        }
        return aggregated, raw_metadata


class ClimateEngineNDVIProvider(NDVIProvider):
    provider_name = "climate_engine"
    citation_url = CLIMATE_ENGINE_DOCS_URL

    def __init__(
        self,
        *,
        api_key_env: str,
        base_url: str,
        dataset: str,
        variable: str,
        area_reducer: str,
        timeout_seconds: int = 30,
        retries: int = 2,
        backoff_seconds: float = 0.5,
    ):
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.dataset = dataset
        self.variable = variable
        self.area_reducer = area_reducer
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()

    def _api_key(self) -> str:
        value = os.getenv(self.api_key_env, "").strip()
        if not value:
            raise RuntimeError(
                f"Climate Engine NDVI requires the {self.api_key_env} environment variable. "
                f"See {CLIMATE_ENGINE_REGISTRATION_URL} and {CLIMATE_ENGINE_AUTH_URL}."
            )
        return value

    def get_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str = "raw",
    ) -> tuple[pd.DataFrame, Any]:
        feature = _normalize_geojson_input(aoi_geojson)
        coordinates = feature["geometry"]["coordinates"][0]
        headers = {"Authorization": self._api_key(), "Accept": "application/json"}
        params = {
            "dataset": self.dataset,
            "variable": self.variable,
            "start_date": pd.Timestamp(start_date).strftime("%Y-%m-%d"),
            "end_date": pd.Timestamp(end_date).strftime("%Y-%m-%d"),
            "coordinates": json.dumps(coordinates),
            "area_reducer": self.area_reducer,
            "export_format": "json",
        }
        url = f"{self.base_url}/timeseries/native/coordinates"

        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                frame = parse_climate_engine_ndvi_response(payload, aoi_id)
                return aggregate_ndvi_series(frame, temporal_aggregation), payload
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError(f"Climate Engine NDVI request failed: {last_exc}")


class AppEEARSNDVIProvider(NDVIProvider):
    provider_name = "appeears"
    citation_url = APPEEARS_DOCS_URL

    def __init__(
        self,
        *,
        username_env: str,
        password_env: str,
        timeout_seconds: int = 30,
    ):
        self.username_env = username_env
        self.password_env = password_env
        self.timeout_seconds = timeout_seconds

    def get_history(
        self,
        aoi_geojson: dict[str, Any],
        *,
        aoi_id: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        cloud_cover_max: float | None = None,
        sensor: str | None = None,
        temporal_aggregation: str = "raw",
    ) -> tuple[pd.DataFrame, Any]:
        username = os.getenv(self.username_env, "").strip()
        password = os.getenv(self.password_env, "").strip()
        if not username or not password:
            raise RuntimeError(
                f"Legacy AppEEARS NDVI requires {self.username_env} and {self.password_env}. See {APPEEARS_DOCS_URL}."
            )
        raise NotImplementedError(
            "AppEEARS NDVI is retained as an optional legacy scaffold only. "
            "RangeIQ now defaults to earth_search_stac for live NDVI history."
        )
