"""Ranch-wide Sentinel-2 greenness (NDVI), built up a little each hour.

The older per-pasture pull opened the red and near-infrared images once for every pasture and every
scene (29 pastures x ~120 scenes x 2 bands, about 7,000 remote reads on Clear Creek Ranch), which takes
hours on a small server. Here each scene is read once for the whole ranch:

* one STAC search over the ranch's bounding box (Earth Search, Sentinel-2 L2A, free, no key);
* per scene, one windowed read each of red (B04), near-infrared (B08) and the scene classification
  (SCL, used to drop cloud, cloud shadow, snow, water and no-data pixels);
* per-pasture mean NDVI from a rasterized pasture mask, kept only if at least half of the pasture
  was clear in that scene.

Results go in a small SQLite file, so each run only reads scenes it has not seen. Runs stop after a
time budget; the newest scenes are done first (current conditions), then older ones fill the
same-season baseline.

Greenness anomaly = median NDVI over the last 30 days compared with the median for the same
+/-20-day window of the year in earlier years (needs at least 2 earlier years).
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import requests

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
CLEAR_SCL = (4, 5, 7)            # vegetation, bare soil, unclassified (drops no-data, saturated, shadow, cloud, cirrus, snow, water)
MIN_CLEAR_SHARE = 0.5            # a pasture's value counts only if at least half of it was clear in the scene
MAX_ATTEMPTS = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UpdateReport:
    scenes_found: int = 0
    scenes_done_before: int = 0
    scenes_read: int = 0
    scenes_failed: int = 0
    scenes_left: int = 0
    seconds: float = 0.0
    stopped_for_time: bool = False
    error: str | None = None

    def text(self) -> str:
        if self.error:
            return f"greenness update failed: {self.error}"
        tail = f", {self.scenes_left} left for the next runs" if self.scenes_left else ""
        return (f"greenness: read {self.scenes_read} new scene(s) in {self.seconds:.0f}s "
                f"({self.scenes_done_before + self.scenes_read}/{self.scenes_found} done{tail})")


class RanchNDVIStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ranch_meta (workspace_id TEXT PRIMARY KEY, geometry_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scenes (
                    workspace_id TEXT NOT NULL, scene_id TEXT NOT NULL, scene_date TEXT NOT NULL,
                    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, note TEXT, processed_at TEXT,
                    PRIMARY KEY (workspace_id, scene_id));
                CREATE TABLE IF NOT EXISTS pasture_ndvi (
                    workspace_id TEXT NOT NULL, pasture_id TEXT NOT NULL, scene_id TEXT NOT NULL, scene_date TEXT NOT NULL,
                    ndvi REAL NOT NULL, clear_share REAL NOT NULL,
                    PRIMARY KEY (workspace_id, pasture_id, scene_id));
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def reset_if_boundary_changed(self, workspace_id: str, geometry_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT geometry_hash FROM ranch_meta WHERE workspace_id = ?", (workspace_id,)).fetchone()
            if row is not None and row["geometry_hash"] == geometry_hash:
                return False
            conn.execute("DELETE FROM scenes WHERE workspace_id = ?", (workspace_id,))
            conn.execute("DELETE FROM pasture_ndvi WHERE workspace_id = ?", (workspace_id,))
            conn.execute("INSERT OR REPLACE INTO ranch_meta(workspace_id, geometry_hash) VALUES (?, ?)", (workspace_id, geometry_hash))
        return row is not None

    def scene_states(self, workspace_id: str) -> dict[str, sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM scenes WHERE workspace_id = ?", (workspace_id,)).fetchall()
        return {r["scene_id"]: r for r in rows}

    def save_scene(self, workspace_id: str, scene_id: str, scene_date: str, status: str, values: dict[str, tuple[float, float]],
                   note: str | None = None) -> None:
        with self._connect() as conn:
            prev = conn.execute("SELECT attempts FROM scenes WHERE workspace_id = ? AND scene_id = ?", (workspace_id, scene_id)).fetchone()
            attempts = (prev["attempts"] if prev else 0) + 1
            conn.execute(
                "INSERT OR REPLACE INTO scenes(workspace_id, scene_id, scene_date, status, attempts, note, processed_at) VALUES (?,?,?,?,?,?,?)",
                (workspace_id, scene_id, scene_date, status, attempts, (note or "")[:300], _utc_now().isoformat(timespec="seconds")),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO pasture_ndvi(workspace_id, pasture_id, scene_id, scene_date, ndvi, clear_share) VALUES (?,?,?,?,?,?)",
                [(workspace_id, pid, scene_id, scene_date, float(v), float(c)) for pid, (v, c) in values.items()],
            )

    def history(self, workspace_id: str) -> pd.DataFrame:
        with self._connect() as conn:
            rows = conn.execute("SELECT pasture_id, scene_date, ndvi, clear_share, scene_id FROM pasture_ndvi WHERE workspace_id = ?",
                                (workspace_id,)).fetchall()
        frame = pd.DataFrame([dict(r) for r in rows], columns=["pasture_id", "scene_date", "ndvi", "clear_share", "scene_id"])
        if not frame.empty:
            frame["scene_date"] = pd.to_datetime(frame["scene_date"])
        return frame


# --- geometry ---------------------------------------------------------------------------------
def _ring_geometry(value: Any) -> dict[str, Any]:
    ring = json.loads(value) if isinstance(value, str) else value
    if isinstance(ring, dict):  # already GeoJSON
        return ring
    ring = [list(map(float, p[:2])) for p in ring]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def pasture_geometries(pastures: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {str(r["pasture_id"]): _ring_geometry(r["geometry"]) for r in pastures.to_dict("records")}


def geometry_hash(geoms: dict[str, dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(geoms, sort_keys=True).encode()).hexdigest()[:16]


def _bbox(geoms: Iterable[dict[str, Any]]) -> list[float]:
    xs, ys = [], []
    for g in geoms:
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    xs.append(x); ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


# --- STAC ---------------------------------------------------------------------------------------
def tile_of(item: dict[str, Any]) -> str:
    props = item.get("properties", {})
    return str(props.get("grid:code") or props.get("s2:mgrs_tile") or (str(item.get("id", "")).split("_") + ["", ""])[1])


def thin_scenes(items: list[dict[str, Any]], per_month: int = 2) -> list[dict[str, Any]]:
    """Keep the clearest `per_month` scenes for each month and each satellite tile."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in items:
        when = str(it.get("properties", {}).get("datetime", ""))[:7]
        groups.setdefault((when, tile_of(it)), []).append(it)
    kept = []
    for group in groups.values():
        group.sort(key=lambda it: (float(it.get("properties", {}).get("eo:cloud_cover", 100) or 100), str(it.get("id"))))
        kept.extend(group[:per_month])
    kept.sort(key=lambda it: str(it.get("properties", {}).get("datetime", "")), reverse=True)
    return kept


def search_scenes(bbox: list[float], start: date, end: date, *, cloud_max: float = 30.0, session: requests.Session | None = None,
                  stac_url: str = EARTH_SEARCH_URL, max_pages: int = 20, timeout: int = 30) -> list[dict[str, Any]]:
    session = session or requests.Session()
    body: dict[str, Any] = {
        "collections": [COLLECTION], "bbox": bbox, "limit": 200,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": cloud_max}},
    }
    url, items = f"{stac_url.rstrip('/')}/search", []
    for _ in range(max_pages):
        resp = session.post(url, json=body, timeout=timeout, headers={"Accept": "application/geo+json"})
        resp.raise_for_status()
        payload = resp.json()
        items.extend(payload.get("features", []))
        nxt = next((l for l in payload.get("links", []) if l.get("rel") == "next"), None)
        if not nxt:
            break
        url = nxt.get("href", url)
        body = {**body, **(nxt.get("body") or {})} if nxt.get("method", "GET").upper() == "POST" else body
    return items


def _asset(item: dict[str, Any], *names: str) -> dict[str, Any]:
    assets = item.get("assets", {})
    for name in names:
        if name in assets and str(assets[name].get("href", "")).strip():
            return assets[name]
    raise KeyError(f"scene {item.get('id')} has none of {names}")


def _scale_offset(asset: dict[str, Any]) -> tuple[float, float]:
    bands = asset.get("raster:bands") or [{}]
    return float(bands[0].get("scale", 1.0) or 1.0), float(bands[0].get("offset", 0.0) or 0.0)


# --- one scene, whole ranch -----------------------------------------------------------------------
def scene_pasture_ndvi(item: dict[str, Any], geoms: dict[str, dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Mean NDVI and clear share per pasture for one scene, reading each band once for the whole ranch."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.transform import array_bounds
    from rasterio.warp import transform_geom
    from rasterio.windows import Window, from_bounds

    red_a, nir_a = _asset(item, "red", "B04"), _asset(item, "nir", "B08")
    scl_a = _asset(item, "scl", "SCL")
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
                      GDAL_HTTP_MULTIRANGE="YES", VSI_CACHE="TRUE", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
        with rasterio.open(red_a["href"]) as red_ds:
            crs = red_ds.crs
            proj = {pid: transform_geom("EPSG:4326", crs, g) for pid, g in geoms.items()}
            minx, miny, maxx, maxy = _bbox(proj.values())
            win = from_bounds(minx - 20, miny - 20, maxx + 20, maxy + 20, transform=red_ds.transform)
            c0, r0 = math.floor(win.col_off), math.floor(win.row_off)
            win = Window(c0, r0, math.ceil(win.col_off + win.width) - c0, math.ceil(win.row_off + win.height) - r0)
            try:
                win = win.intersection(Window(0, 0, red_ds.width, red_ds.height))
            except Exception:  # noqa: BLE001 - rasterio raises WindowError when they don't overlap
                return {}
            if win.width < 1 or win.height < 1:
                return {}
            red = red_ds.read(1, window=win, masked=True).astype("float32")
            tfm = red_ds.window_transform(win)
        h, w = red.shape
        with rasterio.open(nir_a["href"]) as nir_ds:
            nir = nir_ds.read(1, window=from_bounds(*array_bounds(h, w, tfm), transform=nir_ds.transform), out_shape=(h, w),
                              masked=True, resampling=Resampling.nearest).astype("float32")
        with rasterio.open(scl_a["href"]) as scl_ds:
            scl = scl_ds.read(1, window=from_bounds(*array_bounds(h, w, tfm), transform=scl_ds.transform), out_shape=(h, w),
                              resampling=Resampling.nearest)

    rs, ro = _scale_offset(red_a)
    ns, no = _scale_offset(nir_a)
    r = red.filled(0) * rs + ro
    n = nir.filled(0) * ns + no
    clear = (~np.ma.getmaskarray(red)) & (~np.ma.getmaskarray(nir)) & np.isin(scl, CLEAR_SCL) & (red.filled(0) > 0) & ((r + n) > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.clip((n - r) / (n + r), -1.0, 1.0)

    ids = list(proj)
    labels = rasterize([(proj[pid], i + 1) for i, pid in enumerate(ids)], out_shape=(h, w), transform=tfm, fill=0, dtype="uint16")
    pixel_area = abs(tfm.a * tfm.e)
    out: dict[str, tuple[float, float]] = {}
    for i, pid in enumerate(ids, start=1):
        inside = labels == i
        expected = max(_polygon_area(proj[pid]) / pixel_area, 1.0)   # pixels outside this tile count as not clear
        good = inside & clear
        share = float(good.sum()) / expected
        if share >= MIN_CLEAR_SHARE:
            out[pid] = (round(float(np.median(ndvi[good])), 4), round(min(share, 1.0), 3))
    return out


def _polygon_area(geom: dict[str, Any]) -> float:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    total = 0.0
    for poly in polys:
        for k, ring in enumerate(poly):
            a = 0.0
            for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
                a += x0 * y1 - x1 * y0
            total += abs(a) / 2 * (1 if k == 0 else -1)
    return total


# --- incremental update ---------------------------------------------------------------------------
def update_ranch_ndvi(
    store: RanchNDVIStore,
    workspace_id: str,
    pastures: pd.DataFrame,
    *,
    today: date | None = None,
    history_years: int = 4,
    budget_seconds: float = 300.0,
    search: Callable[..., list[dict[str, Any]]] = search_scenes,
    read_scene: Callable[[dict[str, Any], dict[str, dict[str, Any]]], dict[str, tuple[float, float]]] = scene_pasture_ndvi,
    clock: Callable[[], float] = time.monotonic,
) -> UpdateReport:
    report = UpdateReport()
    started = clock()
    today = today or _utc_now().date()
    geoms = pasture_geometries(pastures)
    store.reset_if_boundary_changed(workspace_id, geometry_hash(geoms))
    try:
        items = thin_scenes(search(_bbox(geoms.values()), date(today.year - history_years, today.month, 1), today))
    except Exception as exc:  # noqa: BLE001 - network problems are reported, not raised
        report.error = f"Sentinel-2 search failed ({type(exc).__name__}: {str(exc)[:150]})"
        return report
    states = store.scene_states(workspace_id)
    report.scenes_found = len(items)
    todo = []
    for it in items:
        st = states.get(str(it.get("id")))
        if st is not None and (st["status"] in {"done", "empty"} or st["attempts"] >= MAX_ATTEMPTS):
            report.scenes_done_before += 1
        else:
            todo.append(it)
    for k, it in enumerate(todo):                    # newest first
        if clock() - started > budget_seconds:
            report.stopped_for_time = True
            report.scenes_left = len(todo) - k
            break
        scene_id = str(it.get("id"))
        scene_day = str(it.get("properties", {}).get("datetime", ""))[:10]
        try:
            values = read_scene(it, geoms)
            store.save_scene(workspace_id, scene_id, scene_day, "done" if values else "empty", values)
            report.scenes_read += 1
        except Exception as exc:  # noqa: BLE001 - one bad scene must not stop the rest
            store.save_scene(workspace_id, scene_id, scene_day, "error", {}, note=f"{type(exc).__name__}: {exc}")
            report.scenes_failed += 1
    report.seconds = clock() - started
    return report


def greenness_anomalies(history: pd.DataFrame, today: date, *, window_days: int = 30, season_days: int = 20,
                        min_years: int = 2) -> dict[str, dict[str, Any]]:
    """Per pasture: recent median NDVI vs. the same time of year in earlier years."""
    out: dict[str, dict[str, Any]] = {}
    if history.empty:
        return out
    today_ts = pd.Timestamp(today)
    for pid, g in history.groupby("pasture_id"):
        g = g.sort_values("scene_date")
        recent = g[g["scene_date"] > today_ts - pd.Timedelta(days=window_days)]
        if recent.empty:
            recent = g[g["scene_date"] > today_ts - pd.Timedelta(days=window_days + 15)]
        info: dict[str, Any] = {"as_of": g["scene_date"].max().date().isoformat(), "anomaly_pct": None, "years": 0}
        if not recent.empty:
            current = float(recent["ndvi"].median())
            center = recent["scene_date"].max()
            yearly = []
            for back in range(1, 12):
                c = center - pd.DateOffset(years=back)
                same = g[(g["scene_date"] >= c - pd.Timedelta(days=season_days + window_days // 2))
                         & (g["scene_date"] <= c + pd.Timedelta(days=season_days))]
                if not same.empty:
                    yearly.append(float(same["ndvi"].median()))
            info.update({"current": round(current, 3), "years": len(yearly)})
            if len(yearly) >= min_years:
                normal = float(np.mean(yearly))
                info["normal"] = round(normal, 3)
                if normal > 0.05 and math.isfinite(current):
                    info["anomaly_pct"] = round((current - normal) / normal * 100, 1)
        out[str(pid)] = info
    return out
