"""Ranch-wide Sentinel-2 greenness: one read per scene for all pastures, incremental, time-limited."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ranch_ai.vegetation.ranch_ndvi import (
    RanchNDVIStore,
    greenness_anomalies,
    scene_pasture_ndvi,
    thin_scenes,
    update_ranch_ndvi,
)


def _pastures():
    # two 0.01 x 0.01 degree pastures side by side near Alpine, TX (~1.1 km squares)
    a = [[-103.70, 30.30], [-103.69, 30.30], [-103.69, 30.31], [-103.70, 30.31], [-103.70, 30.30]]
    b = [[-103.69, 30.30], [-103.68, 30.30], [-103.68, 30.31], [-103.69, 30.31], [-103.69, 30.30]]
    return pd.DataFrame({"pasture_id": ["A", "B"], "geometry": [a, b]})


def _item(i: int, day: str, cloud: float = 5.0, tile: str = "13RFL") -> dict:
    return {"id": f"S2B_{tile}_{day.replace('-', '')}_{i}", "properties": {"datetime": f"{day}T17:30:00Z", "eo:cloud_cover": cloud, "grid:code": tile}}


def test_thin_keeps_clearest_two_per_month_and_tile_newest_first():
    items = [_item(1, "2026-09-02", 20), _item(2, "2026-09-12", 1), _item(3, "2026-09-22", 9), _item(4, "2026-09-05", 3, tile="13RGL"),
             _item(5, "2026-10-01", 50)]
    kept = thin_scenes(items)
    assert [k["id"] for k in kept][0].endswith("_5")
    sept_13rfl = [k["id"] for k in kept if "13RFL" in k["id"] and "202609" in k["id"]]
    assert sorted(sept_13rfl) == ["S2B_13RFL_20260912_2", "S2B_13RFL_20260922_3"]
    assert any("13RGL" in k["id"] for k in kept)


def test_update_is_incremental_and_respects_the_time_budget(tmp_path):
    store = RanchNDVIStore(tmp_path / "ndvi.sqlite")
    items = [_item(i, f"2026-{m:02d}-1{i}") for m in range(1, 10) for i in (1, 2)]
    reads = []

    def read(item, geoms):
        reads.append(item["id"])
        return {pid: (0.3, 0.9) for pid in geoms}

    ticks = iter(range(0, 10_000, 10))                # every clock() call is 10 s later
    rep = update_ranch_ndvi(store, "ws", _pastures(), today=date(2026, 10, 1), budget_seconds=55,
                            search=lambda *a, **k: items, read_scene=read, clock=lambda: next(ticks))
    assert rep.stopped_for_time and rep.scenes_read == len(reads) and 0 < len(reads) < len(items)
    first = set(reads)
    assert reads[0] == max(items, key=lambda it: it["properties"]["datetime"])["id"]        # newest first
    reads.clear()
    rep2 = update_ranch_ndvi(store, "ws", _pastures(), today=date(2026, 10, 1), budget_seconds=1e9,
                             search=lambda *a, **k: items, read_scene=read)
    assert not first & set(reads) and rep2.scenes_left == 0                                  # never re-reads a scene
    assert len(store.history("ws")) == 2 * len(items)


def test_failed_scene_is_retried_then_given_up(tmp_path):
    store = RanchNDVIStore(tmp_path / "ndvi.sqlite")
    items = [_item(1, "2026-09-02")]

    def boom(item, geoms):
        raise OSError("read timed out")

    for _ in range(3):
        rep = update_ranch_ndvi(store, "ws", _pastures(), today=date(2026, 10, 1), search=lambda *a, **k: items, read_scene=boom)
        assert rep.scenes_failed == 1
    rep = update_ranch_ndvi(store, "ws", _pastures(), today=date(2026, 10, 1), search=lambda *a, **k: items, read_scene=boom)
    assert rep.scenes_failed == 0 and rep.scenes_done_before == 1


def test_search_failure_is_reported_not_raised(tmp_path):
    def down(*a, **k):
        raise ConnectionError("no route")

    rep = update_ranch_ndvi(RanchNDVIStore(tmp_path / "n.sqlite"), "ws", _pastures(), search=down)
    assert rep.error and "search failed" in rep.text()


def test_anomaly_compares_with_same_season_in_earlier_years():
    rows = []
    for year, value in ((2023, 0.40), (2024, 0.44), (2025, 0.42)):
        rows += [("A", f"{year}-09-20", value), ("A", f"{year}-10-05", value)]
    rows += [("A", "2026-09-25", 0.30), ("A", "2026-10-08", 0.32)]
    rows += [("B", "2026-10-08", 0.5)]                                          # no earlier years yet
    hist = pd.DataFrame(rows, columns=["pasture_id", "scene_date", "ndvi"]).assign(scene_date=lambda d: pd.to_datetime(d.scene_date))
    out = greenness_anomalies(hist, date(2026, 10, 10))
    assert out["A"]["years"] == 3 and out["A"]["anomaly_pct"] == pytest.approx((0.31 - 0.42) / 0.42 * 100, abs=0.2)
    assert out["B"]["anomaly_pct"] is None and out["B"]["as_of"] == "2026-10-08"


def test_one_read_per_band_gives_every_pasture_its_value(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from rasterio.warp import transform

    # Local stand-ins for the red / near-infrared (10 m) and scene classification (20 m) images in UTM 13N.
    xs, ys = transform("EPSG:4326", "EPSG:32613", [-103.705, -103.675], [30.315, 30.295])
    west, north = xs[0], ys[0]
    w, h = int((xs[1] - xs[0]) / 10) + 1, int((ys[0] - ys[1]) / 10) + 1
    cols = np.arange(w)[None, :].repeat(h, 0)
    split = int((transform("EPSG:4326", "EPSG:32613", [-103.69], [30.305])[0][0] - west) / 10)
    red = np.where(cols < split, 1000 + 1000, 1000 + 500).astype("uint16")      # DN with the -0.1 offset: A red 0.1, B red 0.05
    nir = np.where(cols < split, 1000 + 3000, 1000 + 4500).astype("uint16")     # A nir 0.3 (NDVI 0.5), B nir 0.45 (NDVI 0.8)
    scl = np.full((h // 2 + 1, w // 2 + 1), 4, "uint8")
    scl[: int((h // 2 + 1) * 0.375), :] = 9                                       # cloud over the northern quarter of the pastures
    paths = {}
    for name, arr, res in (("red", red, 10), ("nir", nir, 10), ("scl", scl, 20)):
        paths[name] = tmp_path / f"{name}.tif"
        with rasterio.open(paths[name], "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype=arr.dtype,
                           crs="EPSG:32613", transform=from_origin(west, north, res, res), nodata=0) as ds:
            ds.write(arr, 1)
    band = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
    item = {"id": "S2_test", "properties": {}, "assets": {"red": {"href": str(paths["red"]), **band},
                                                          "nir": {"href": str(paths["nir"]), **band},
                                                          "scl": {"href": str(paths["scl"])}}}
    from ranch_ai.vegetation.ranch_ndvi import pasture_geometries

    out = scene_pasture_ndvi(item, pasture_geometries(_pastures()))
    assert out["A"][0] == pytest.approx(0.5, abs=0.01) and out["B"][0] == pytest.approx(0.8, abs=0.01)
    assert 0.5 <= out["A"][1] < 0.95                                             # cloudy part left out
