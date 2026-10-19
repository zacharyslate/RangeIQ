"""USGS 3DEP lidar-derived elevation retrieval for a saved ranch boundary.

Default source: the USGS 3D Elevation Program (3DEP) dynamic bare-earth DEM
ImageServer. Where USGS lidar exists (e.g. TX_WestTexas_B7_2018, QL2 for the
Alpine / Caja Caliente parcel) the service serves the 1 m lidar-derived DEM;
elsewhere it falls back to coarser 3DEP layers. We request the raster in the
local UTM zone so pixels are square metres, cache it as a GeoTIFF, and fall
back to deterministic synthetic terrain when the service is unreachable so
the dashboard never breaks.

The request intentionally uses ``exportImage`` with ``f=image`` (binary
GeoTIFF). See the service directory for the parameter contract:
https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from ranch_ai.config import Settings, settings as default_settings

NODATA_VALUE = -9999.0


@dataclass
class TerrainGrid:
    """A north-up elevation grid in a projected (metre) CRS."""

    elevation_m: np.ndarray  # shape (rows, cols); row 0 is the northern edge; NaN = nodata
    transform: Any  # rasterio.Affine
    crs_epsg: int
    resolution_m: float
    source: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.elevation_m.shape)  # type: ignore[return-value]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        rows, cols = self.elevation_m.shape
        minx = float(self.transform.c)
        maxy = float(self.transform.f)
        maxx = minx + cols * float(self.transform.a)
        miny = maxy + rows * float(self.transform.e)
        return minx, miny, maxx, maxy

    def valid_fraction(self) -> float:
        if self.elevation_m.size == 0:
            return 0.0
        return float(np.isfinite(self.elevation_m).mean())


@dataclass
class TerrainLoadResult:
    grid: TerrainGrid | None
    status: dict[str, Any]


def utm_epsg_for(lon: float, lat: float) -> int:
    """WGS84 / UTM EPSG code for a lon/lat (326xx north, 327xx south)."""
    zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def _pasture_rings(pastures: pd.DataFrame) -> list[list[list[float]]]:
    rings: list[list[list[float]]] = []
    for geometry in pastures.get("geometry", pd.Series(dtype=object)):
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if geometry:
            rings.append([[float(pt[0]), float(pt[1])] for pt in geometry])
    if not rings:
        raise ValueError("No pasture geometry is available to build terrain for.")
    return rings


def compute_request_bounds(pastures: pd.DataFrame, buffer_m: float) -> tuple[int, tuple[float, float, float, float]]:
    """Project every boundary vertex to local UTM and return a buffered bbox."""
    from rasterio.warp import transform as warp_transform

    rings = _pasture_rings(pastures)
    lons = [pt[0] for ring in rings for pt in ring]
    lats = [pt[1] for ring in rings for pt in ring]
    epsg = utm_epsg_for(float(np.mean(lons)), float(np.mean(lats)))
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{epsg}", lons, lats)
    minx, maxx = min(xs) - buffer_m, max(xs) + buffer_m
    miny, maxy = min(ys) - buffer_m, max(ys) + buffer_m
    return epsg, (minx, miny, maxx, maxy)


def plan_raster_size(
    bounds: tuple[float, float, float, float],
    resolution_m: float,
    max_pixels_per_side: int,
    max_total_pixels: int | None = None,
) -> tuple[int, int, float]:
    """Return (width, height, effective_resolution_m), coarsening if the AOI is large."""
    minx, miny, maxx, maxy = bounds
    span_x, span_y = maxx - minx, maxy - miny
    if span_x <= 0 or span_y <= 0:
        raise ValueError("Terrain request bounds must have positive width and height.")
    resolution = max(float(resolution_m), 0.5)
    longest = max(span_x, span_y)
    if longest / resolution > max_pixels_per_side:
        resolution = longest / max_pixels_per_side
    if max_total_pixels and (span_x / resolution) * (span_y / resolution) > max_total_pixels:
        resolution = math.sqrt(span_x * span_y / max_total_pixels)
    width = max(int(math.ceil(span_x / resolution)), 2)
    height = max(int(math.ceil(span_y / resolution)), 2)
    return width, height, resolution


def build_export_image_params(
    bounds: tuple[float, float, float, float],
    epsg: int,
    width: int,
    height: int,
) -> dict[str, str]:
    minx, miny, maxx, maxy = bounds
    # Snap the requested extent to whole pixels so the returned transform is exact.
    res_x = (maxx - minx) / width
    res_y = (maxy - miny) / height
    return {
        "bbox": f"{minx:.3f},{miny:.3f},{minx + width * res_x:.3f},{miny + height * res_y:.3f}",
        "bboxSR": str(epsg),
        "imageSR": str(epsg),
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "noData": str(NODATA_VALUE),
        "noDataInterpretation": "esriNoDataMatchAny",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }


def read_geotiff_bytes(
    payload: bytes,
    *,
    fallback_epsg: int,
    fallback_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray, Any, int]:
    """Decode a GeoTIFF. If the payload lacks georeferencing, rebuild it from the requested bbox."""
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds

    with MemoryFile(payload) as memfile:
        with memfile.open() as dataset:
            band = dataset.read(1).astype("float32")
            nodata = dataset.nodata
            transform = dataset.transform
            epsg = dataset.crs.to_epsg() if dataset.crs is not None else None
    if transform.is_identity and fallback_bounds is not None:
        rows, cols = band.shape
        transform = from_bounds(*fallback_bounds, cols, rows)
    if nodata is not None:
        band[band == nodata] = np.nan
    # Guard against services that ignore noData and return large negative fill.
    band[(band < -500.0) | (band > 9000.0)] = np.nan
    return band, transform, int(epsg or fallback_epsg)


def synthetic_terrain(
    bounds: tuple[float, float, float, float],
    epsg: int,
    width: int,
    height: int,
    *,
    seed: int = 42,
    base_elevation_m: float = 1380.0,
) -> TerrainGrid:
    """Deterministic, plausible high-desert terrain for offline mode and tests."""
    from rasterio.transform import from_bounds

    minx, miny, maxx, maxy = bounds
    rng = np.random.default_rng(seed)
    xs = np.linspace(0.0, 1.0, width, dtype="float32")
    ys = np.linspace(1.0, 0.0, height, dtype="float32")  # row 0 = north
    grid_x, grid_y = np.meshgrid(xs, ys)
    span = max(maxx - minx, maxy - miny)

    elevation = base_elevation_m + 0.012 * span * grid_x + 0.006 * span * grid_y
    for _ in range(4):
        cx, cy = rng.uniform(0.1, 0.9, size=2)
        amplitude = rng.uniform(0.004, 0.02) * span
        sigma = rng.uniform(0.08, 0.25)
        elevation += amplitude * np.exp(-(((grid_x - cx) ** 2 + (grid_y - cy) ** 2) / (2 * sigma**2)))
    # A shallow drainage running roughly north-south.
    channel = 0.004 * span * np.exp(-((grid_x - 0.45 - 0.1 * np.sin(grid_y * 6.0)) ** 2) / 0.003)
    elevation -= channel
    elevation += rng.normal(0.0, 0.05, size=elevation.shape)

    return TerrainGrid(
        elevation_m=elevation.astype("float32"),
        transform=from_bounds(minx, miny, maxx, maxy, width, height),
        crs_epsg=epsg,
        resolution_m=(maxx - minx) / width,
        source="mock",
        detail={"note": "Synthetic terrain for offline mode. Not real elevation."},
    )


def grid_to_geotiff_bytes(grid: TerrainGrid) -> bytes:
    """Serialize a terrain grid as a compressed GeoTIFF (for download/export)."""
    from rasterio.io import MemoryFile

    rows, cols = grid.elevation_m.shape
    data = np.where(np.isfinite(grid.elevation_m), grid.elevation_m, NODATA_VALUE).astype("float32")
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="float32",
            crs=f"EPSG:{grid.crs_epsg}",
            transform=grid.transform,
            nodata=NODATA_VALUE,
            compress="deflate",
        ) as dataset:
            dataset.write(data, 1)
            dataset.update_tags(source=grid.source, units="metres", vertical_datum="NAVD88" if grid.source == "usgs_3dep" else "synthetic")
        return memfile.read()


class USGS3DEPClient:
    def __init__(self, image_server_url: str, *, timeout_seconds: int = 60, user_agent: str = "RangeIQ/0.1"):
        self.export_url = image_server_url.rstrip("/") + "/exportImage"
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def fetch(self, params: dict[str, str]) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(self.export_url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if "json" in content_type or response.content[:1] == b"{":
                    # ArcGIS returns HTTP 200 with a JSON error body on bad requests.
                    raise RuntimeError(f"3DEP exportImage returned an error: {response.text[:300]}")
                return response.content
            except Exception as exc:  # noqa: BLE001 - surfaced through status
                last_exc = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"3DEP exportImage request failed: {last_exc}")


class TerrainService:
    def __init__(self, app_settings: Settings = default_settings, cache_dir: Path | None = None):
        self.settings = app_settings
        self.config = app_settings.terrain
        self.cache_dir = Path(cache_dir) if cache_dir is not None else app_settings.terrain_cache_dir

    # -- cache -------------------------------------------------------------
    def _cache_key(self, provider: str, epsg: int, bounds: tuple[float, ...], width: int, height: int) -> str:
        payload = json.dumps(
            {
                "provider": provider,
                "url": self.config.image_server_url,
                "epsg": epsg,
                "bounds": [round(value, 1) for value in bounds],
                "size": [width, height],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _read_cache(self, key: str) -> TerrainGrid | None:
        tif_path = self.cache_dir / f"{key}.tif"
        meta_path = self.cache_dir / f"{key}.json"
        if not tif_path.exists() or not meta_path.exists():
            return None
        age_days = (time.time() - tif_path.stat().st_mtime) / 86400.0
        if age_days > self.config.cache_ttl_days:
            return None
        try:
            import rasterio

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            with rasterio.open(tif_path) as dataset:
                band = dataset.read(1).astype("float32")
                nodata = dataset.nodata
                transform = dataset.transform
            if nodata is not None:
                band[band == nodata] = np.nan
            return TerrainGrid(
                elevation_m=band,
                transform=transform,
                crs_epsg=int(meta["crs_epsg"]),
                resolution_m=float(meta["resolution_m"]),
                source=str(meta["source"]),
                detail={**meta.get("detail", {}), "cache": "hit"},
            )
        except Exception:  # noqa: BLE001 - corrupt cache just refetches
            return None

    def _write_cache(self, key: str, grid: TerrainGrid) -> None:
        try:
            import rasterio

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            rows, cols = grid.elevation_m.shape
            data = np.where(np.isfinite(grid.elevation_m), grid.elevation_m, NODATA_VALUE).astype("float32")
            with rasterio.open(
                self.cache_dir / f"{key}.tif",
                "w",
                driver="GTiff",
                height=rows,
                width=cols,
                count=1,
                dtype="float32",
                crs=f"EPSG:{grid.crs_epsg}",
                transform=grid.transform,
                nodata=NODATA_VALUE,
                compress="deflate",
                predictor=3,
            ) as dataset:
                dataset.write(data, 1)
            meta = {
                "crs_epsg": grid.crs_epsg,
                "resolution_m": grid.resolution_m,
                "source": grid.source,
                "detail": grid.detail,
            }
            (self.cache_dir / f"{key}.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        except Exception:  # noqa: BLE001 - caching is best effort
            pass

    # -- public ------------------------------------------------------------
    def load(
        self,
        pastures: pd.DataFrame,
        *,
        provider: str | None = None,
        buffer_m: float | None = None,
        resolution_m: float | None = None,
        seed: int = 42,
    ) -> TerrainLoadResult:
        requested_provider = (provider or self.config.provider or "usgs_3dep").strip().lower()
        buffer = float(self.config.buffer_m if buffer_m is None else buffer_m)
        resolution = float(self.config.resolution_m if resolution_m is None else resolution_m)

        epsg, bounds = compute_request_bounds(pastures, buffer)
        width, height, effective_resolution = plan_raster_size(
            bounds, resolution, self.config.max_pixels_per_side, self.config.max_total_pixels
        )
        status: dict[str, Any] = {
            "requested_provider": requested_provider,
            "crs_epsg": epsg,
            "width_px": width,
            "height_px": height,
            "resolution_m": round(effective_resolution, 3),
            "buffer_m": buffer,
        }

        if requested_provider == "usgs_3dep":
            key = self._cache_key(requested_provider, epsg, bounds, width, height)
            cached = self._read_cache(key)
            if cached is not None:
                status.update({"mode": "live-cached", "provider": "usgs_3dep", "error": None})
                return TerrainLoadResult(grid=cached, status=status)
            params = build_export_image_params(bounds, epsg, width, height)
            try:
                client = USGS3DEPClient(
                    self.config.image_server_url,
                    timeout_seconds=self.config.timeout_seconds,
                    user_agent=self.config.user_agent,
                )
                requested_bounds = tuple(float(value) for value in params["bbox"].split(","))
                band, transform, returned_epsg = read_geotiff_bytes(
                    client.fetch(params),
                    fallback_epsg=epsg,
                    fallback_bounds=requested_bounds,  # type: ignore[arg-type]
                )
                grid = TerrainGrid(
                    elevation_m=band,
                    transform=transform,
                    crs_epsg=returned_epsg,
                    resolution_m=float(abs(transform.a)),
                    source="usgs_3dep",
                    detail={
                        "service": self.config.image_server_url,
                        "product": "3DEP bare-earth DEM (dynamic, best available; 1 m where lidar exists)",
                        "vertical_datum": "NAVD88 (metres)",
                        "requested_at": pd.Timestamp.now("UTC").isoformat(),
                        "request": params,
                    },
                )
                if grid.valid_fraction() < 0.5:
                    raise RuntimeError(
                        f"3DEP returned mostly nodata ({grid.valid_fraction():.0%} valid) for this extent."
                    )
                self._write_cache(key, grid)
                status.update({"mode": "live", "provider": "usgs_3dep", "error": None})
                return TerrainLoadResult(grid=grid, status=status)
            except Exception as exc:  # noqa: BLE001 - fall back so the tab still renders
                status.update({"error": str(exc)})
                grid = synthetic_terrain(bounds, epsg, width, height, seed=seed)
                status.update({"mode": "fallback-mock", "provider": "mock"})
                return TerrainLoadResult(grid=grid, status=status)

        grid = synthetic_terrain(bounds, epsg, width, height, seed=seed)
        status.update({"mode": "mock", "provider": "mock", "error": None})
        return TerrainLoadResult(grid=grid, status=status)
