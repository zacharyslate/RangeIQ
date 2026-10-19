"""Ranch setup from the app (owner only): pasture boundary, pasture names, ranch name and time zone.

Writes the same files the old desktop console used, so the worker reads them unchanged:
  config/workspaces/<ws>/config.yaml           ranch name, time zone, location (merged over defaults)
  config/workspaces/<ws>/dashboard_state.json  saved_boundary {filename, path}; pasture_names {id: name}
  data/user/workspaces/<ws>/saved_boundary.<ext>

Standard library only (plus PyYAML), so the light API process never loads pandas or GDAL. The full
parse happens in the worker; here we only check the file is a usable boundary and count its pastures.
After a change, a request file in data/refresh/ asks the worker to rebuild that ranch now
(a systemd path unit starts it; otherwise the hourly run picks it up).
"""

from __future__ import annotations

import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAX_BOUNDARY_BYTES = 15 * 1024 * 1024
ALLOWED = {".kml", ".kmz", ".geojson", ".json"}
TIMEZONES = ["America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/New_York",
             "America/Anchorage", "Pacific/Honolulu"]


def normalize_workspace_id(raw: str) -> str:          # same rule as ranch_ai.config.normalize_workspace_id
    c = re.sub(r"[^a-z0-9_-]+", "-", (raw or "").strip().lower())
    return re.sub(r"-{2,}", "-", c).strip("-_") or "workspace"


def paths(workspace_id: str, root: Path = PROJECT_ROOT) -> dict[str, Path]:
    ws = normalize_workspace_id(workspace_id)
    prof = root / "config" / "workspaces" / ws
    return {"config": prof / "config.yaml", "state": prof / "dashboard_state.json",
            "boundary_dir": root / "data" / "user" / "workspaces" / ws, "refresh": root / "data" / "refresh" / f"{ws}.request"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# --- boundary check ------------------------------------------------------------------------------
def _kml_polygons(text: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(text)
    out = []
    for pm in root.iter():
        if not pm.tag.endswith("Placemark"):
            continue
        name = next((c.text for c in pm if c.tag.endswith("name") and c.text), None)
        rings = [el.text for el in pm.iter() if el.tag.endswith("coordinates") and el.text]
        polys = [el for el in pm.iter() if el.tag.endswith("Polygon")]
        if not polys or not rings:
            continue
        pts = []
        for chunk in rings[0].split():
            parts = chunk.split(",")
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))
        if len(pts) >= 3:
            out.append({"name": (name or "").strip() or None, "points": pts})
    return out


def _geojson_polygons(text: bytes) -> list[dict[str, Any]]:
    data = json.loads(text)
    feats = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
    out = []
    for f in feats:
        g = (f or {}).get("geometry") or {}
        coords = g.get("coordinates") or []
        ring = coords[0] if g.get("type") == "Polygon" and coords else coords[0][0] if g.get("type") == "MultiPolygon" and coords else None
        if ring and len(ring) >= 3:
            props = f.get("properties") or {}
            out.append({"name": props.get("name") or props.get("Name") or props.get("pasture_name"), "points": [(float(p[0]), float(p[1])) for p in ring]})
    return out


def check_boundary(filename: str, data: bytes) -> list[dict[str, Any]]:
    """Polygons found in the file (name + points). Raises ValueError with a plain message."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("Use a KML, KMZ or GeoJSON file (Google Earth: right-click the folder → Save Place As → KMZ).")
    if not data or len(data) > MAX_BOUNDARY_BYTES:
        raise ValueError("That file is empty or too big (15 MB max).")
    try:
        if suffix == ".kmz":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                kml = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
                if kml is None:
                    raise ValueError("That KMZ has no KML inside.")
                polys = _kml_polygons(z.read(kml))
        elif suffix == ".kml":
            polys = _kml_polygons(data)
        else:
            polys = _geojson_polygons(data)
    except (ET.ParseError, zipfile.BadZipFile, ValueError, KeyError, TypeError, IndexError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("That"):
            raise
        raise ValueError("Couldn't read that file. Export the pastures from Google Earth as KML or KMZ and try again.") from None
    if not polys:
        raise ValueError("No pasture outlines (polygons) were found in that file. Lines and pins don't count.")
    if len(polys) > 500:
        raise ValueError("That file has more than 500 shapes; is it the right one?")
    for p in polys:
        for lon, lat in p["points"]:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Some coordinates are out of range. Is the file in latitude/longitude (WGS84)?")
    return polys


# --- saving ---------------------------------------------------------------------------------------
def save_boundary(workspace_id: str, filename: str, data: bytes, *, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    polys = check_boundary(filename, data)
    p = paths(workspace_id, root)
    suffix = Path(filename).suffix.lower()
    p["boundary_dir"].mkdir(parents=True, exist_ok=True)
    for old in p["boundary_dir"].glob("saved_boundary.*"):
        old.unlink(missing_ok=True)
    dest = p["boundary_dir"] / f"saved_boundary{suffix}"
    dest.write_bytes(data)
    state = _read_json(p["state"])
    state.update({"workspace_id": normalize_workspace_id(workspace_id), "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "saved_boundary": {"filename": Path(filename).name, "path": str(dest)}})
    state.pop("pasture_names", None)                      # new outlines, new ids
    p["state"].parent.mkdir(parents=True, exist_ok=True)
    p["state"].write_text(json.dumps(state, indent=2), encoding="utf-8")
    # Put the ranch's weather point in the middle of the pastures.
    xs = [x for poly in polys for x, _ in poly["points"]]
    ys = [y for poly in polys for _, y in poly["points"]]
    set_ranch(workspace_id, latitude=round((min(ys) + max(ys)) / 2, 6), longitude=round((min(xs) + max(xs)) / 2, 6), root=root)
    request_refresh(workspace_id, root=root)
    return {"filename": Path(filename).name, "pastures": len(polys), "names": [p["name"] for p in polys if p["name"]][:50]}


def set_ranch(workspace_id: str, *, name: str | None = None, timezone: str | None = None, latitude: float | None = None,
              longitude: float | None = None, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if timezone is not None and timezone not in TIMEZONES:
        raise ValueError("Pick a time zone from the list.")
    if name is not None:
        name = name.strip()[:80]
        if not name:
            raise ValueError("The ranch needs a name.")
    p = paths(workspace_id, root)
    cfg = _read_yaml(p["config"])
    ranch = cfg.get("ranch") if isinstance(cfg.get("ranch"), dict) else {}
    for key, value in (("name", name), ("timezone", timezone), ("latitude", latitude), ("longitude", longitude)):
        if value is not None:
            ranch[key] = value
    cfg["ranch"] = ranch
    p["config"].parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        p["config"].write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    else:  # pragma: no cover
        p["config"].write_text(json.dumps(cfg), encoding="utf-8")
    if name is not None or timezone is not None:
        request_refresh(workspace_id, root=root)
    return {k: ranch.get(k) for k in ("name", "timezone", "latitude", "longitude")}


def set_pasture_names(workspace_id: str, names: dict[str, str], *, root: Path = PROJECT_ROOT) -> dict[str, str]:
    p = paths(workspace_id, root)
    state = _read_json(p["state"])
    current = state.get("pasture_names") if isinstance(state.get("pasture_names"), dict) else {}
    for pid, nm in (names or {}).items():
        nm = str(nm or "").strip()[:60]
        if nm:
            current[str(pid)[:64]] = nm
        else:
            current.pop(str(pid), None)
    state["pasture_names"] = current
    p["state"].parent.mkdir(parents=True, exist_ok=True)
    p["state"].write_text(json.dumps(state, indent=2), encoding="utf-8")
    request_refresh(workspace_id, root=root)
    return current


def describe(workspace_id: str, *, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    p = paths(workspace_id, root)
    cfg, state = _read_yaml(p["config"]), _read_json(p["state"])
    ranch = cfg.get("ranch") if isinstance(cfg.get("ranch"), dict) else {}
    boundary = state.get("saved_boundary") if isinstance(state.get("saved_boundary"), dict) else {}
    return {"ranch": {"name": ranch.get("name"), "timezone": ranch.get("timezone") or "America/Chicago"},
            "boundary_file": boundary.get("filename") if boundary.get("path") and Path(boundary["path"]).exists() else None,
            "pasture_names": state.get("pasture_names") or {}, "timezones": TIMEZONES,
            "refresh_pending": p["refresh"].exists()}


def request_refresh(workspace_id: str, *, root: Path = PROJECT_ROOT) -> None:
    f = paths(workspace_id, root)["refresh"]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")


def take_refresh_requests(*, root: Path = PROJECT_ROOT) -> list[str]:
    """Workspaces that asked for a rebuild (and clear the requests)."""
    folder = root / "data" / "refresh"
    out = []
    for f in sorted(folder.glob("*.request")) if folder.exists() else []:
        out.append(f.stem)
        f.unlink(missing_ok=True)
    return out
