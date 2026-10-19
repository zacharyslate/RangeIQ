"""Terrain derivatives and per-pasture terrain summaries.

Grazing-capacity slope classes follow Holechek (1988), as tabulated for cattle
in NMSU Extension Guide B-829, "Estimating Carrying Capacity on Rangelands"
(Spackman & Ward, 2023): 0-10 % slope no reduction, 11-30 % -> 30 %,
31-60 % -> 60 %, >60 % ungrazable. https://pubs.nmsu.edu/_b/B-829.pdf

Those classes were defined for field-scale slope, not 1 m lidar micro-relief,
so the grazing slope is computed on a block-averaged surface (default 10 m).
Treat the adjustment as a starting point to be checked against observed
cattle use, not a calibrated truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ranch_ai.terrain.dem_client import TerrainGrid

M_TO_FT = 3.280839895

HOLECHEK_SLOPE_CLASSES: list[tuple[str, float, float, float]] = [
    # label, lower bound (exclusive, %), upper bound (inclusive, %), capacity reduction
    ("0-10%", -np.inf, 10.0, 0.0),
    ("11-30%", 10.0, 30.0, 0.30),
    ("31-60%", 30.0, 60.0, 0.60),
    (">60%", 60.0, np.inf, 1.0),
]

ASPECT_SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


@dataclass
class TerrainDerivatives:
    slope_deg: np.ndarray
    slope_pct: np.ndarray
    aspect_deg: np.ndarray  # compass bearing the slope faces (downslope), 0 = north
    hillshade: np.ndarray  # 0..1


def slope_aspect(elevation_m: np.ndarray, resolution_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slope (deg, %) and aspect from a north-up grid using central differences."""
    # float32 throughout: halves peak memory on large ranches versus float64.
    elevation = np.asarray(elevation_m, dtype="float32")
    d_row, d_col = np.gradient(elevation, np.float32(resolution_m))
    dz_dx = d_col  # east
    dz_dy = np.negative(d_row, out=d_row)  # north (row index increases southward)
    gradient = np.hypot(dz_dx, dz_dy)
    aspect = np.degrees(np.arctan2(-dz_dx, -dz_dy))
    aspect += 360.0
    aspect %= 360.0
    aspect[gradient < 1e-6] = np.nan
    del dz_dx, dz_dy, d_col
    slope_pct = gradient * np.float32(100.0)
    slope_deg = np.degrees(np.arctan(gradient))
    return slope_deg.astype("float32", copy=False), slope_pct.astype("float32", copy=False), aspect.astype("float32", copy=False)


def hillshade(
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    *,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
) -> np.ndarray:
    zenith = np.radians(90.0 - altitude_deg)
    slope = np.radians(slope_deg)
    aspect = np.radians(np.nan_to_num(aspect_deg, nan=0.0))
    shade = np.cos(zenith) * np.cos(slope) + np.sin(zenith) * np.sin(slope) * np.cos(np.radians(azimuth_deg) - aspect)
    return np.clip(shade, 0.0, 1.0).astype("float32")


def compute_derivatives(grid: TerrainGrid) -> TerrainDerivatives:
    slope_deg, slope_pct, aspect_deg = slope_aspect(grid.elevation_m, grid.resolution_m)
    return TerrainDerivatives(
        slope_deg=slope_deg,
        slope_pct=slope_pct,
        aspect_deg=aspect_deg,
        hillshade=hillshade(slope_deg, aspect_deg),
    )


def block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    """NaN-aware block average; edge rows/cols that do not fill a block are dropped."""
    if factor <= 1:
        return np.asarray(array, dtype="float32")
    rows, cols = array.shape
    trimmed = array[: rows - rows % factor, : cols - cols % factor]
    if trimmed.size == 0:
        return np.asarray(array, dtype="float32")
    blocks = trimmed.reshape(trimmed.shape[0] // factor, factor, trimmed.shape[1] // factor, factor)
    valid = np.isfinite(blocks)
    counts = valid.sum(axis=(1, 3))
    sums = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, sums / counts, np.nan).astype("float32")


def grazing_scale_slope_pct(grid: TerrainGrid, window_m: float) -> np.ndarray:
    """Slope (%) computed on a block-averaged DEM, broadcast back to the native grid."""
    factor = max(int(round(window_m / max(grid.resolution_m, 1e-6))), 1)
    if factor <= 1:
        return slope_aspect(grid.elevation_m, grid.resolution_m)[1]
    coarse = block_mean(grid.elevation_m, factor)
    if min(coarse.shape) < 3:
        return slope_aspect(grid.elevation_m, grid.resolution_m)[1]
    coarse_slope = slope_aspect(coarse, grid.resolution_m * factor)[1]
    upsampled = np.repeat(np.repeat(coarse_slope, factor, axis=0), factor, axis=1)
    rows, cols = grid.elevation_m.shape
    out = np.full((rows, cols), np.nan, dtype="float32")
    out[: upsampled.shape[0], : upsampled.shape[1]] = upsampled[:rows, :cols]
    # Fill the dropped edge strip with the nearest coarse values.
    if upsampled.shape[0] < rows:
        out[upsampled.shape[0] :, :] = out[upsampled.shape[0] - 1, :]
    if upsampled.shape[1] < cols:
        out[:, upsampled.shape[1] :] = out[:, [upsampled.shape[1] - 1]]
    return out


def _ring_geojson(ring: list[list[float]]) -> dict:
    return {"type": "Polygon", "coordinates": [ring]}


def pasture_mask(grid: TerrainGrid, ring_lonlat: list[list[float]]) -> np.ndarray:
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    geometry = transform_geom("EPSG:4326", f"EPSG:{grid.crs_epsg}", _ring_geojson(ring_lonlat))
    return geometry_mask([geometry], out_shape=grid.elevation_m.shape, transform=grid.transform, invert=True)


def classify_holechek(slope_pct: np.ndarray) -> dict[str, float]:
    values = slope_pct[np.isfinite(slope_pct)]
    if values.size == 0:
        return {label: float("nan") for label, *_ in HOLECHEK_SLOPE_CLASSES}
    shares: dict[str, float] = {}
    for label, lower, upper, _ in HOLECHEK_SLOPE_CLASSES:
        shares[label] = float(((values > lower) & (values <= upper)).mean())
    return shares


def grazeable_fraction(shares: dict[str, float]) -> float:
    total = 0.0
    for label, _, _, reduction in HOLECHEK_SLOPE_CLASSES:
        share = shares.get(label, 0.0)
        if share != share:  # NaN
            return float("nan")
        total += share * (1.0 - reduction)
    return float(total)


def dominant_aspect(aspect_deg: np.ndarray, slope_pct: np.ndarray, min_slope_pct: float = 3.0) -> str:
    usable = aspect_deg[np.isfinite(aspect_deg) & (slope_pct >= min_slope_pct)]
    if usable.size == 0:
        return "flat"
    sectors = ((usable + 22.5) % 360.0 // 45.0).astype(int)
    counts = np.bincount(sectors, minlength=8)
    return ASPECT_SECTORS[int(np.argmax(counts))]


def pasture_terrain_stats(
    grid: TerrainGrid,
    pastures: pd.DataFrame,
    *,
    grazing_slope_window_m: float = 10.0,
    derivatives: TerrainDerivatives | None = None,
) -> pd.DataFrame:
    derivs = derivatives or compute_derivatives(grid)
    grazing_slope = grazing_scale_slope_pct(grid, grazing_slope_window_m)
    rows: list[dict] = []
    for record in pastures.itertuples(index=False):
        ring = record.geometry if not isinstance(record.geometry, str) else json.loads(record.geometry)
        mask = pasture_mask(grid, ring)
        inside = mask & np.isfinite(grid.elevation_m)
        pixel_count = int(mask.sum())
        valid_count = int(inside.sum())
        row = {
            "pasture_id": record.pasture_id,
            "name": getattr(record, "name", record.pasture_id),
            "acres": float(getattr(record, "acres", float("nan"))),
            "dem_pixels": pixel_count,
            "dem_coverage_pct": round(100.0 * valid_count / pixel_count, 1) if pixel_count else 0.0,
        }
        if valid_count == 0:
            rows.append(row)
            continue
        elevation_ft = grid.elevation_m[inside] * M_TO_FT
        slope_inside = derivs.slope_pct[inside]
        shares = classify_holechek(grazing_slope[inside])
        fraction = grazeable_fraction(shares)
        row.update(
            {
                "elev_min_ft": round(float(np.nanmin(elevation_ft)), 1),
                "elev_mean_ft": round(float(np.nanmean(elevation_ft)), 1),
                "elev_max_ft": round(float(np.nanmax(elevation_ft)), 1),
                "relief_ft": round(float(np.nanmax(elevation_ft) - np.nanmin(elevation_ft)), 1),
                "slope_mean_pct_1m": round(float(np.nanmean(slope_inside)), 1),
                "slope_p90_pct_1m": round(float(np.nanpercentile(slope_inside, 90)), 1),
                "slope_mean_pct_grazing": round(float(np.nanmean(grazing_slope[inside])), 1),
                "dominant_aspect": dominant_aspect(derivs.aspect_deg[inside], slope_inside),
                **{f"share_slope_{label}": round(100.0 * share, 1) for label, share in shares.items()},
                "slope_grazeable_fraction": round(fraction, 3),
                "slope_adjusted_acres": round(row["acres"] * fraction, 2) if fraction == fraction else float("nan"),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


# -- 3D helpers ---------------------------------------------------------------

def downsample_for_display(grid: TerrainGrid, layer: np.ndarray, max_side: int = 260) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return x (m east), y (m north, ascending), z (elevation m) and the colour layer, strided for WebGL."""
    rows, cols = grid.elevation_m.shape
    stride = max(int(np.ceil(max(rows, cols) / max_side)), 1)
    z = grid.elevation_m[::stride, ::stride][::-1, :]
    color = layer[::stride, ::stride][::-1, :]
    minx, miny, _, _ = grid.bounds
    res = grid.resolution_m * stride
    x = (np.arange(z.shape[1]) + 0.5) * res
    # After flipping, row 0 is the southern edge.
    y = (np.arange(z.shape[0]) + 0.5) * res
    del minx, miny
    return x, y, z, color


def drape_ring(grid: TerrainGrid, ring_lonlat: list[list[float]], spacing_m: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Densify a boundary ring and sample DEM heights so it can be drawn on the surface.

    Returns x/y in metres relative to the grid's south-west corner and z in metres.
    """
    from rasterio.warp import transform as warp_transform

    lons = [pt[0] for pt in ring_lonlat]
    lats = [pt[1] for pt in ring_lonlat]
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{grid.crs_epsg}", lons, lats)
    step = spacing_m or max(grid.resolution_m * 2.0, 1.0)
    dense_x: list[float] = []
    dense_y: list[float] = []
    for (x0, y0), (x1, y1) in zip(zip(xs[:-1], ys[:-1]), zip(xs[1:], ys[1:])):
        length = float(np.hypot(x1 - x0, y1 - y0))
        steps = max(int(length // step), 1)
        for t in np.linspace(0.0, 1.0, steps, endpoint=False):
            dense_x.append(x0 + (x1 - x0) * t)
            dense_y.append(y0 + (y1 - y0) * t)
    dense_x.append(xs[-1])
    dense_y.append(ys[-1])

    # Map coordinates -> pixel (col, row) with the inverse affine's coefficients directly.
    # (Avoids `*` / `@` on Affine, whose support differs between affine versions.)
    inv = ~grid.transform
    xs_arr, ys_arr = np.asarray(dense_x), np.asarray(dense_y)
    cols = inv.a * xs_arr + inv.b * ys_arr + inv.c
    rows = inv.d * xs_arr + inv.e * ys_arr + inv.f
    rows_n, cols_n = grid.elevation_m.shape
    r = np.clip(np.floor(rows), 0, rows_n - 1).astype(int)
    c = np.clip(np.floor(cols), 0, cols_n - 1).astype(int)
    z = grid.elevation_m[r, c].astype(float).tolist()
    minx, miny, _, _ = grid.bounds
    return np.asarray(dense_x) - minx, np.asarray(dense_y) - miny, np.asarray(z)
