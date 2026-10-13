"""Phone-sized 3D terrain assets for a ranch (built by the worker, served by the API).

Same design as the Marfa Lights 3D map: a quantized uint16 height grid plus
a texture draped over it, drawn in the browser with three.js.

* height.bin: little-endian uint16, row 0 = north edge; elevation = z0 + q * zscale (metres, NAVD88)
* texture: USGS NAIP natural-color aerial photo exported over the same
  extent; falls back to a shaded-relief image when NAIP can't be reached
* meta: grid size, extent in metres, pasture outlines in local metres
  (x east, y north from the south-west corner)
"""

from __future__ import annotations

import io
import json
import math
from typing import Any

import numpy as np
import pandas as pd
import requests

from ranch_ai.terrain.analysis import block_mean, compute_derivatives
from ranch_ai.terrain.dem_client import TerrainGrid

NAIP_EXPORT_URL = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
MAX_VERTICES_PER_SIDE = 256
TEXTURE_MAX_PX = 1024


def _fill_nan(z: np.ndarray) -> np.ndarray:
    if np.isfinite(z).all():
        return z
    out = z.copy()
    finite = np.isfinite(out)
    if not finite.any():
        return np.zeros_like(out)
    # Fill gaps row-wise by nearest valid value, then any remaining with the median.
    for row in out:
        bad = ~np.isfinite(row)
        if bad.any() and (~bad).any():
            idx = np.where(~bad)[0]
            row[bad] = np.interp(np.where(bad)[0], idx, row[idx])
    out[~np.isfinite(out)] = float(np.nanmedian(z))
    return out


def height_grid(grid: TerrainGrid, max_side: int = MAX_VERTICES_PER_SIDE) -> tuple[np.ndarray, float]:
    """Downsample the DEM to at most max_side vertices per side. Returns (z, cell_m)."""
    rows, cols = grid.elevation_m.shape
    factor = max(int(math.ceil(max(rows, cols) / max_side)), 1)
    z = block_mean(grid.elevation_m, factor) if factor > 1 else grid.elevation_m.astype("float32")
    return _fill_nan(z), grid.resolution_m * factor


def quantize(z: np.ndarray) -> tuple[bytes, float, float]:
    z0 = float(np.min(z))
    span = float(np.max(z)) - z0
    zscale = max(span / 65535.0, 0.001)
    q = np.clip(np.round((z - z0) / zscale), 0, 65535).astype("<u2")
    return q.tobytes(), z0, zscale


def dequantize(payload: bytes, z0: float, zscale: float, nx: int, ny: int) -> np.ndarray:
    return (np.frombuffer(payload, dtype="<u2").astype("float32") * zscale + z0).reshape(ny, nx)


def local_outlines(grid: TerrainGrid, pastures: pd.DataFrame, *, mesh_height_m: float | None = None) -> list[dict[str, Any]]:
    """Outlines in metres from the mesh's south-west corner.

    The mesh keeps the grid's north-west corner; block averaging may trim a few
    cells off the south/east edges, so the south edge is maxy - mesh_height_m.
    """
    from rasterio.warp import transform as warp_transform

    minx, miny, _, maxy = grid.bounds
    if mesh_height_m is not None:
        miny = maxy - mesh_height_m
    out = []
    for record in pastures.to_dict("records"):
        ring = record["geometry"] if not isinstance(record["geometry"], str) else json.loads(record["geometry"])
        xs, ys = warp_transform("EPSG:4326", f"EPSG:{grid.crs_epsg}", [p[0] for p in ring], [p[1] for p in ring])
        out.append({
            "id": str(record["pasture_id"]),
            "name": str(record.get("name") or record["pasture_id"]),
            "ring": [[round(x - minx, 1), round(y - miny, 1)] for x, y in zip(xs, ys)],
        })
    return out


def naip_texture(grid: TerrainGrid, *, timeout: int = 60, user_agent: str = "RangeIQ") -> bytes:
    """Natural-color NAIP aerial photo over the grid extent, as JPEG bytes (raises on failure)."""
    minx, miny, maxx, maxy = grid.bounds
    span_x, span_y = maxx - minx, maxy - miny
    scale = TEXTURE_MAX_PX / max(span_x, span_y)
    # No point asking for finer than NAIP's ~0.6 m pixels.
    scale = min(scale, 1 / 0.6)
    width, height = max(int(span_x * scale), 64), max(int(span_y * scale), 64)
    params = {
        "bbox": f"{minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}",
        "bboxSR": str(grid.crs_epsg),
        "imageSR": str(grid.crs_epsg),
        "size": f"{width},{height}",
        "format": "jpg",
        "compressionQuality": "80",
        "renderingRule": json.dumps({"rasterFunction": "NaturalColor"}),
        "f": "image",
    }
    response = requests.get(NAIP_EXPORT_URL, params=params, timeout=timeout, headers={"User-Agent": user_agent})
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").startswith("image/") or response.content[:1] == b"{":
        raise RuntimeError(f"NAIP export returned {response.headers.get('Content-Type')}: {response.text[:200]}")
    return response.content


def relief_texture(grid: TerrainGrid) -> bytes:
    """Fallback texture: elevation tint x hillshade, as PNG bytes."""
    from PIL import Image

    z, _ = height_grid(grid, max_side=TEXTURE_MAX_PX)
    sub = TerrainGrid(elevation_m=z, transform=grid.transform, crs_epsg=grid.crs_epsg,
                      resolution_m=grid.resolution_m * grid.elevation_m.shape[1] / z.shape[1], source=grid.source)
    shade = compute_derivatives(sub).hillshade
    t = (z - z.min()) / max(float(np.ptp(z)), 1e-6)
    low, high = np.array([96, 120, 70]), np.array([196, 168, 120])  # grassland green -> caliche tan
    rgb = (low[None, None, :] * (1 - t[..., None]) + high[None, None, :] * t[..., None])
    rgb = rgb * (0.45 + 0.55 * shade[..., None])
    buffer = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype("uint8")).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_terrain_assets(
    grid: TerrainGrid,
    pastures: pd.DataFrame,
    *,
    fetch_imagery: bool = True,
    user_agent: str = "RangeIQ",
) -> dict[str, Any]:
    z, cell_m = height_grid(grid)
    payload, z0, zscale = quantize(z)
    ny, nx = z.shape
    texture_source = "relief"
    texture: bytes | None = None
    texture_mime = "image/png"
    texture_note = None
    if fetch_imagery and grid.source == "usgs_3dep":
        try:
            texture = naip_texture(grid, user_agent=user_agent)
            texture_source, texture_mime = "naip", "image/jpeg"
        except Exception as exc:  # noqa: BLE001 - relief fallback is fine
            texture_note = f"Aerial photo unavailable ({str(exc)[:120]}); showing shaded relief."
    if texture is None:
        texture = relief_texture(grid)
    finite = grid.elevation_m[np.isfinite(grid.elevation_m)]
    meta = {
        "nx": nx,
        "ny": ny,
        "cell_m": round(cell_m, 3),
        "width_m": round(nx * cell_m, 1),
        "height_m": round(ny * cell_m, 1),
        "z0": round(z0, 3),
        "zscale": zscale,
        "z_min_m": round(float(finite.min()), 2) if finite.size else None,
        "z_max_m": round(float(finite.max()), 2) if finite.size else None,
        "crs_epsg": grid.crs_epsg,
        "dem_resolution_m": round(grid.resolution_m, 2),
        "dem_source": grid.source,
        "texture_source": texture_source,
        "texture_note": texture_note,
        "outlines": local_outlines(grid, pastures, mesh_height_m=ny * cell_m),
    }
    return {"meta": meta, "height": payload, "texture": texture, "texture_mime": texture_mime}
