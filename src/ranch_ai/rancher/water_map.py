"""Mapped water on the ranch from the USGS National Hydrography Dataset (NHD, high resolution).

Ponds, stock tanks (NHD "Reservoir"), playas and marshes come from the Waterbody layer (12); springs,
wells, dams and small reservoirs from the Point layer (0) of
https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer. Polygons are reduced to a centre
point and an area. NHD was mapped from older imagery and misses many dirt tanks, so the app labels these
as "USGS water map" and lets the crew save the real ones as their own places.

Cached per ranch for 30 days; it rarely changes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import requests

NHD_URL = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
CACHE_DAYS = 30
BUFFER_DEG = 0.002          # ~200 m around the ranch

WATERBODY_KIND = {436: "tank", 390: "pond", 361: "playa", 466: "marsh"}
POINT_KIND = {458: "spring", 488: "well", 343: "dam", 436: "tank"}
KIND_LABEL = {"tank": "Stock tank / reservoir", "pond": "Pond / lake", "playa": "Playa", "marsh": "Marsh",
              "spring": "Spring / seep", "well": "Well", "dam": "Dam"}
INTERMITTENT_FCODES = {39001, 39005, 39006, 43614, 46601}


def _ring_bbox(pastures) -> list[float]:
    xs, ys = [], []
    for geom in pastures["geometry"]:
        ring = json.loads(geom) if isinstance(geom, str) else geom
        for p in ring:
            xs.append(float(p[0])); ys.append(float(p[1]))
    return [min(xs) - BUFFER_DEG, min(ys) - BUFFER_DEG, max(xs) + BUFFER_DEG, max(ys) + BUFFER_DEG]


def _query(layer: int, bbox: list[float], fields: str, get: Callable[..., Any], timeout: int) -> list[dict[str, Any]]:
    params = {
        "geometry": ",".join(f"{v:.6f}" for v in bbox), "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "true", "outSR": "4326",
        "f": "geojson", "resultRecordCount": "2000",
    }
    resp = get(f"{NHD_URL}/{layer}/query", params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(str(payload["error"])[:200])
    return payload.get("features", [])


def _centre(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """Area-weighted centre of the largest polygon ring (good enough for a pin on a pond)."""
    polys = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon":
        polys = [polys]
    best, best_area = None, -1.0
    for poly in polys:
        ring = poly[0] if poly else []
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            cross = x0 * y1 - x1 * y0
            a += cross; cx += (x0 + x1) * cross; cy += (y0 + y1) * cross
        if abs(a) > best_area and a != 0:
            best_area, best = abs(a), (cy / (3 * a), cx / (3 * a))
    return best


def fetch_water_features(pastures, *, get: Callable[..., Any] | None = None, timeout: int = 30) -> list[dict[str, Any]]:
    get = get or requests.Session().get
    bbox = _ring_bbox(pastures)
    out: list[dict[str, Any]] = []
    for f in _query(12, bbox, "GNIS_NAME,FTYPE,FCODE,AREASQKM,PERMANENT_IDENTIFIER", get, timeout):
        p = f.get("properties", {}) or {}
        kind = WATERBODY_KIND.get(int(p.get("FTYPE") or 0))
        centre = _centre(f.get("geometry") or {})
        if kind is None or centre is None:
            continue
        acres = round(float(p.get("AREASQKM") or 0) * 247.105, 2)
        out.append({"id": "nhd-" + str(p.get("PERMANENT_IDENTIFIER") or len(out)), "kind": kind, "label": KIND_LABEL[kind],
                    "name": p.get("GNIS_NAME") or None, "lat": round(centre[0], 6), "lon": round(centre[1], 6), "acres": acres,
                    "intermittent": int(p.get("FCODE") or 0) in INTERMITTENT_FCODES})
    for f in _query(0, bbox, "GNIS_NAME,FTYPE,FCODE,PERMANENT_IDENTIFIER", get, timeout):
        p = f.get("properties", {}) or {}
        kind = POINT_KIND.get(int(p.get("FTYPE") or 0))
        coords = (f.get("geometry") or {}).get("coordinates")
        if kind is None or not coords:
            continue
        out.append({"id": "nhd-" + str(p.get("PERMANENT_IDENTIFIER") or len(out)), "kind": kind, "label": KIND_LABEL[kind],
                    "name": p.get("GNIS_NAME") or None, "lat": round(float(coords[1]), 6), "lon": round(float(coords[0]), 6), "acres": None,
                    "intermittent": False})
    return out


def water_features(workspace_id: str, pastures, cache_dir: Path, **kw) -> dict[str, Any]:
    """Cached for CACHE_DAYS. Returns {"features": [...], "as_of": iso, "error": str | None}."""
    cache = Path(cache_dir) / f"nhd_{''.join(c for c in workspace_id if c.isalnum() or c in '-_')}.json"
    bbox = _ring_bbox(pastures)
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("bbox") == [round(v, 5) for v in bbox] and time.time() - cached.get("fetched", 0) < CACHE_DAYS * 86400:
            return {"features": cached["features"], "as_of": cached.get("as_of"), "error": None}
    except (OSError, ValueError, KeyError):
        cached = None
    try:
        feats = fetch_water_features(pastures, **kw)
    except Exception as exc:  # noqa: BLE001 - optional layer
        if cached:
            return {"features": cached.get("features", []), "as_of": cached.get("as_of"), "error": f"using saved copy ({type(exc).__name__})"}
        return {"features": [], "as_of": None, "error": f"USGS water map unavailable ({type(exc).__name__})"}
    as_of = time.strftime("%Y-%m-%d")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"bbox": [round(v, 5) for v in bbox], "fetched": time.time(), "as_of": as_of, "features": feats}), encoding="utf-8")
    return {"features": feats, "as_of": as_of, "error": None}
