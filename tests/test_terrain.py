from __future__ import annotations

import json

import numpy as np
import pytest
from rasterio.transform import from_bounds

from ranch_ai.config import Settings
from ranch_ai.terrain import (
    TerrainGrid,
    TerrainService,
    build_export_image_params,
    compute_derivatives,
    compute_request_bounds,
    drape_ring,
    grid_to_geotiff_bytes,
    pasture_terrain_stats,
    plan_raster_size,
    utm_epsg_for,
)
from ranch_ai.terrain.analysis import block_mean, classify_holechek, grazeable_fraction, slope_aspect
from ranch_ai.terrain.dem_client import read_geotiff_bytes
from ranch_ai.utils.io import load_pastures
from ranch_ai.visualization.terrain_plots import TERRAIN_LAYERS, build_terrain_figure


def _plane_grid(dz_dx: float, dz_dy: float, size: int = 60, res: float = 1.0) -> TerrainGrid:
    """Planar DEM: z = dz_dx * east + dz_dy * north, north-up."""
    east = np.arange(size) * res
    north = (np.arange(size) * res)[::-1]
    grid_e, grid_n = np.meshgrid(east, north)
    elevation = 1000.0 + dz_dx * grid_e + dz_dy * grid_n
    return TerrainGrid(
        elevation_m=elevation.astype("float32"),
        transform=from_bounds(500000.0, 3000000.0, 500000.0 + size * res, 3000000.0 + size * res, size, size),
        crs_epsg=32613,
        resolution_m=res,
        source="test",
    )


def test_utm_zone_for_alpine_texas():
    assert utm_epsg_for(-103.51, 29.61) == 32613
    assert utm_epsg_for(-99.4, 32.4) == 32614  # Baird, TX
    assert utm_epsg_for(151.2, -33.9) == 32756


def test_slope_and_aspect_on_known_planes():
    # Rising to the east at 20 % -> slope 20 %, faces west (downslope = 270 deg).
    grid = _plane_grid(0.20, 0.0)
    _, slope_pct, aspect = slope_aspect(grid.elevation_m, grid.resolution_m)
    assert np.nanmedian(slope_pct) == pytest.approx(20.0, rel=1e-3)
    assert np.nanmedian(aspect) == pytest.approx(270.0, abs=0.5)

    # Rising to the north -> faces south.
    grid = _plane_grid(0.0, 0.10)
    _, slope_pct, aspect = slope_aspect(grid.elevation_m, grid.resolution_m)
    assert np.nanmedian(slope_pct) == pytest.approx(10.0, rel=1e-3)
    assert np.nanmedian(aspect) == pytest.approx(180.0, abs=0.5)


def test_flat_ground_has_undefined_aspect():
    grid = _plane_grid(0.0, 0.0)
    _, slope_pct, aspect = slope_aspect(grid.elevation_m, grid.resolution_m)
    assert float(np.nanmax(slope_pct)) == 0.0
    assert np.isnan(aspect).all()


def test_holechek_classes_and_grazeable_fraction():
    slopes = np.array([5.0, 10.0, 10.1, 30.0, 45.0, 61.0, 90.0, np.nan])
    shares = classify_holechek(slopes)
    assert shares["0-10%"] == pytest.approx(2 / 7)
    assert shares["11-30%"] == pytest.approx(2 / 7)
    assert shares["31-60%"] == pytest.approx(1 / 7)
    assert shares[">60%"] == pytest.approx(2 / 7)
    expected = (2 / 7) * 1.0 + (2 / 7) * 0.7 + (1 / 7) * 0.4 + (2 / 7) * 0.0
    assert grazeable_fraction(shares) == pytest.approx(expected)


def test_block_mean_ignores_nan():
    array = np.array([[1.0, 3.0, 5.0], [np.nan, 5.0, 7.0], [9.0, 9.0, 9.0]])
    result = block_mean(array, 2)
    assert result.shape == (1, 1)
    assert result[0, 0] == pytest.approx(3.0)


def test_request_bounds_and_params_for_default_ranch():
    pastures = load_pastures()
    epsg, bounds = compute_request_bounds(pastures, buffer_m=100.0)
    assert epsg == 32613
    width, height, resolution = plan_raster_size(bounds, 1.0, 3000)
    assert resolution == pytest.approx(1.0)
    params = build_export_image_params(bounds, epsg, width, height)
    assert params["f"] == "image"
    assert params["format"] == "tiff"
    assert params["pixelType"] == "F32"
    assert params["bboxSR"] == params["imageSR"] == "32613"
    assert params["size"] == f"{width},{height}"
    minx, miny, maxx, maxy = (float(value) for value in params["bbox"].split(","))
    assert (maxx - minx) / width == pytest.approx((maxy - miny) / height, rel=0.01)


def test_large_aoi_coarsens_resolution():
    width, height, resolution = plan_raster_size((0.0, 0.0, 30000.0, 12000.0), 1.0, 3000)
    assert width <= 3000 and height <= 3000
    assert resolution == pytest.approx(10.0)


def test_total_pixel_budget_caps_large_ranches():
    # ~10,000 ac square: 6.36 km per side.
    width, height, resolution = plan_raster_size((0.0, 0.0, 6360.0, 6360.0), 1.0, 3000, 2_500_000)
    assert width * height <= 2_500_000 * 1.01
    assert resolution == pytest.approx(4.02, rel=0.01)
    # Small parcels keep 1 m.
    assert plan_raster_size((0.0, 0.0, 500.0, 300.0), 1.0, 3000, 2_500_000)[2] == pytest.approx(1.0)


def test_default_ranch_stats_match_boundary_area(tmp_path):
    pastures = load_pastures()
    result = TerrainService(Settings(), cache_dir=tmp_path).load(pastures, provider="mock")
    assert result.status["mode"] == "mock"
    stats = pasture_terrain_stats(result.grid, pastures)
    row = stats.iloc[0]
    # One-metre pixels inside a 4.77-acre polygon should be ~19,300 m^2.
    assert row["dem_pixels"] * result.grid.resolution_m**2 == pytest.approx(4.77 * 4046.86, rel=0.03)
    assert row["dem_coverage_pct"] == 100.0
    assert 0.0 <= row["slope_grazeable_fraction"] <= 1.0
    assert row["elev_max_ft"] >= row["elev_min_ft"]


def test_live_provider_falls_back_to_mock_when_unreachable(tmp_path, monkeypatch):
    def boom(self, params):
        raise RuntimeError("network blocked")

    monkeypatch.setattr("ranch_ai.terrain.dem_client.USGS3DEPClient.fetch", boom)
    result = TerrainService(Settings(), cache_dir=tmp_path).load(load_pastures(), provider="usgs_3dep")
    assert result.status["mode"] == "fallback-mock"
    assert "network blocked" in result.status["error"]
    assert result.grid.source == "mock"


def test_live_provider_parses_geotiff_and_uses_cache(tmp_path, monkeypatch):
    pastures = load_pastures()
    calls = {"count": 0}

    def fake_fetch(self, params):
        calls["count"] += 1
        minx, miny, maxx, maxy = (float(value) for value in params["bbox"].split(","))
        width, height = (int(value) for value in params["size"].split(","))
        grid = _plane_grid(0.05, 0.0, size=1)
        grid.elevation_m = np.full((height, width), 1390.0, dtype="float32")
        grid.elevation_m[0, 0] = np.nan
        grid.transform = from_bounds(minx, miny, maxx, maxy, width, height)
        grid.crs_epsg = int(params["imageSR"])
        return grid_to_geotiff_bytes(grid)

    monkeypatch.setattr("ranch_ai.terrain.dem_client.USGS3DEPClient.fetch", fake_fetch)
    service = TerrainService(Settings(), cache_dir=tmp_path)
    first = service.load(pastures, provider="usgs_3dep")
    assert first.status["mode"] == "live"
    assert first.grid.source == "usgs_3dep"
    assert np.isnan(first.grid.elevation_m[0, 0])
    assert np.nanmax(first.grid.elevation_m) == pytest.approx(1390.0)

    second = service.load(pastures, provider="usgs_3dep")
    assert second.status["mode"] == "live-cached"
    assert calls["count"] == 1


def test_geotiff_round_trip_preserves_nodata():
    grid = _plane_grid(0.1, 0.1, size=8)
    grid.elevation_m[2, 3] = np.nan
    band, transform, epsg = read_geotiff_bytes(grid_to_geotiff_bytes(grid), fallback_epsg=0)
    assert epsg == 32613
    assert np.isnan(band[2, 3])
    assert transform.a == pytest.approx(1.0)


def test_ungeoreferenced_tiff_uses_requested_bounds():
    from rasterio.io import MemoryFile

    data = np.full((4, 5), 1400.0, dtype="float32")
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", height=4, width=5, count=1, dtype="float32") as dataset:
            dataset.write(data, 1)
        payload = memfile.read()
    band, transform, epsg = read_geotiff_bytes(payload, fallback_epsg=32613, fallback_bounds=(100.0, 200.0, 110.0, 208.0))
    assert epsg == 32613
    assert transform.c == pytest.approx(100.0)
    assert transform.f == pytest.approx(208.0)
    assert transform.a == pytest.approx(2.0)


def test_drape_ring_and_figure_build(tmp_path):
    pastures = load_pastures()
    grid = TerrainService(Settings(), cache_dir=tmp_path).load(pastures, provider="mock").grid
    bx, by, bz = drape_ring(grid, pastures.geometry.iloc[0])
    assert np.isfinite(bz).all()
    assert bx.min() > 0 and by.min() > 0
    derivatives = compute_derivatives(grid)
    for layer in TERRAIN_LAYERS:
        figure = build_terrain_figure(grid, derivatives, pastures, layer=layer, exaggeration=2.0)
        assert figure.data[0].type == "surface"
        assert len(figure.data) == 1 + len(pastures)


def test_terrain_settings_round_trip_into_config_payload():
    from ranch_ai.config import settings_to_config_payload

    payload = settings_to_config_payload(Settings())
    assert payload["terrain"]["provider"] in {"usgs_3dep", "mock"}
    assert payload["terrain"]["grazing_slope_window_m"] == pytest.approx(10.0)


def test_pasture_frame_with_string_geometry_is_supported(tmp_path):
    pastures = load_pastures().copy()
    pastures["geometry"] = pastures["geometry"].apply(json.dumps)
    grid = TerrainService(Settings(), cache_dir=tmp_path).load(pastures, provider="mock").grid
    stats = pasture_terrain_stats(grid, pastures)
    assert stats.iloc[0]["dem_pixels"] > 0


def test_drape_ring_samples_the_right_cells_without_affine_operators():
    """drape_ring must match rasterio's own rowcol lookup and not depend on Affine `*`/`@` support."""
    from rasterio.transform import rowcol

    grid = _plane_grid(0.3, 0.1, size=40, res=2.0)  # tilted plane, 2 m cells
    ring = [[-103.5, 29.6], [-103.5, 29.6], [-103.5, 29.6], [-103.5, 29.6]]
    # Build a ring in grid coordinates via a tiny projected square, then compare heights.
    from rasterio.warp import transform as warp
    xs = [500010.0, 500050.0, 500050.0, 500010.0, 500010.0]
    ys = [3000010.0, 3000010.0, 3000060.0, 3000060.0, 3000010.0]
    lons, lats = warp(f"EPSG:{grid.crs_epsg}", "EPSG:4326", xs, ys)
    ring = [[lo, la] for lo, la in zip(lons, lats)]
    dx, dy, dz = drape_ring(grid, ring, spacing_m=4.0)
    minx, miny, _, _ = grid.bounds
    for x, y, z in zip(dx + minx, dy + miny, dz):
        r, c = rowcol(grid.transform, x, y)
        r = min(max(r, 0), 39); c = min(max(c, 0), 39)
        assert z == pytest.approx(float(grid.elevation_m[r, c]), abs=1e-3)
    import inspect
    from ranch_ai.terrain import analysis
    assert " @ (" not in inspect.getsource(analysis.drape_ring)
