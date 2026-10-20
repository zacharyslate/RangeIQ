"""Admin helpers for running RangeIQ for one account (server-side only).

    python -m ranch_ai.rancher.admin find  someone@example.com
    python -m ranch_ai.rancher.admin build someone@example.com [--force-live] [--export DIR]

'find' shows the account's ranch and whether a pasture boundary is uploaded.
'build' pulls live data for that ranch now (weather, alerts, rain history,
drought, satellite greenness, RAP, USGS 3DEP lidar terrain, NAIP aerial photo),
stores the phone-app snapshot and 3D terrain, and prints what came back.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ranch_ai.config import normalize_workspace_id, settings as default_settings
from ranch_ai.rancher.store import AppStore
from ranch_ai.services.auth_service import AuthService


def find_account(email: str, auth_db: Path | None = None):
    user = AuthService(auth_db or default_settings.auth_db_path).get_user_by_email(email)
    if user is None:
        raise SystemExit(f"No RangeIQ account with email {email!r}.")
    return user


def describe(user) -> dict:
    from ranch_ai.rancher.worker import workspace_inputs

    workspace_id = normalize_workspace_id(user.workspace_id)
    app_settings, pastures, boundary = workspace_inputs(workspace_id)
    info = {
        "name": user.full_name,
        "ranch": user.ranch_name,
        "address": user.ranch_address,
        "workspace_id": workspace_id,
        "boundary_file": boundary,
        "providers": {
            "weather": app_settings.weather.provider,
            "alerts": app_settings.alerts.provider,
            "rain history": app_settings.public_data.historical_weather.provider,
            "drought": app_settings.public_data.drought.provider,
            "greenness": app_settings.public_data.vegetation.provider,
            "terrain": app_settings.terrain.provider,
        },
    }
    if pastures is not None:
        info["pastures"] = [{"id": r["pasture_id"], "name": r["name"], "acres": round(float(r["acres"]), 1)}
                            for r in pastures.to_dict("records")]
        info["total_acres"] = round(float(pastures["acres"].sum()), 1)
        info["center_lat_lon"] = [round(float(pastures["centroid_lat"].mean()), 5), round(float(pastures["centroid_lon"].mean()), 5)]
    return info


def export(workspace_id: str, store: AppStore, directory: Path) -> list[Path]:
    from ranch_ai.rancher.worker import workspace_inputs
    from ranch_ai.terrain import TerrainService, grid_to_geotiff_bytes, pasture_terrain_stats

    directory.mkdir(parents=True, exist_ok=True)
    written = []
    snapshot = store.latest_snapshot(workspace_id)
    if snapshot:
        path = directory / "snapshot.json"
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8"); written.append(path)
    app_settings, pastures, _ = workspace_inputs(workspace_id)
    if pastures is not None:
        result = TerrainService(app_settings).load(pastures)  # served from the terrain cache after a build
        if result.grid is not None and result.grid.source == "usgs_3dep":
            path = directory / "lidar_dem_1m.tif" if result.grid.resolution_m < 1.5 else directory / "lidar_dem.tif"
            path.write_bytes(grid_to_geotiff_bytes(result.grid)); written.append(path)
            path = directory / "terrain_by_pasture.csv"
            pasture_terrain_stats(result.grid, pastures).to_csv(path, index=False); written.append(path)
    texture = store.terrain_blob(workspace_id, "texture")
    if texture:
        path = directory / ("aerial.jpg" if texture[1] == "image/jpeg" else "relief.png")
        path.write_bytes(texture[0]); written.append(path)
    return written


def diagnose_greenness(workspace_id: str, redact: bool = False) -> int:
    """Step through the Sentinel-2 greenness pull for one pasture and say exactly where it fails."""
    import time

    import pandas as pd
    import requests

    from ranch_ai.rancher.worker import workspace_inputs
    from ranch_ai.vegetation.ndvi_client import EarthSearchSTACNDVIProvider, build_earth_search_query, select_sentinel_2_assets

    app_settings, pastures, _ = workspace_inputs(workspace_id)
    if pastures is None:
        print("No pasture boundary uploaded for this account.")
        return 1
    cfg = app_settings.public_data.vegetation
    record = pastures.iloc[0]
    ring = record["geometry"] if not isinstance(record["geometry"], str) else json.loads(record["geometry"])
    feature = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    label = "first pasture" if redact else f"{record['name']} ({float(record['acres']):.1f} ac)"
    print(f"Pasture: {label}; provider={cfg.provider}; STAC={cfg.earth_search_stac_url}; "
          f"collection={cfg.ndvi_default_collection}; max cloud={cfg.ndvi_cloud_cover_max}%")
    try:
        import rasterio
        print(f"1. rasterio {rasterio.__version__}, GDAL {rasterio.__gdal_version__}: OK")
    except Exception as exc:  # noqa: BLE001
        print(f"1. rasterio import FAILED: {exc}")
        return 1
    end = pd.Timestamp.now().normalize()
    query = build_earth_search_query(feature, start_date=end - pd.Timedelta(days=90), end_date=end,
                                     collection=cfg.ndvi_default_collection, cloud_cover_max=cfg.ndvi_cloud_cover_max, limit=20)
    started = time.time()
    try:
        r = requests.post(f"{cfg.earth_search_stac_url.rstrip('/')}/search", json=query, timeout=30,
                          headers={"Accept": "application/geo+json"})
        print(f"2. STAC search: HTTP {r.status_code} in {time.time() - started:.1f}s")
        if r.status_code >= 400:
            print("   body:", r.text[:400])
            return 1
        items = r.json().get("features", [])
        print(f"   {len(items)} scenes with <= {cfg.ndvi_cloud_cover_max}% cloud in the last 90 days")
        if not items:
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"2. STAC search FAILED: {exc}")
        return 1
    item = items[0]
    try:
        assets = select_sentinel_2_assets(item)
        href = assets["red_asset"]["href"]
        print(f"3. Newest scene {item.get('id')} ({item['properties'].get('datetime')}), red band: {href}")
    except Exception as exc:  # noqa: BLE001
        print(f"3. Scene assets FAILED: {exc}")
        return 1
    try:
        head = requests.get(href, headers={"Range": "bytes=0-1023"}, timeout=30)
        print(f"4. Image download (first 1 KB): HTTP {head.status_code}")
    except Exception as exc:  # noqa: BLE001
        print(f"4. Image download FAILED: {exc}")
        return 1
    provider = EarthSearchSTACNDVIProvider(stac_url=cfg.earth_search_stac_url)
    started = time.time()
    try:
        stats = provider._scene_ndvi_stats(item, feature["geometry"], red_asset=assets["red_asset"], nir_asset=assets["nir_asset"])
        print(f"5. NDVI over the pasture from that scene: {stats['ndvi_mean']:.3f} in {time.time() - started:.1f}s  -> pipeline works")
    except Exception as exc:  # noqa: BLE001
        print(f"5. Reading the image over the pasture FAILED after {time.time() - started:.1f}s: {type(exc).__name__}: {exc}")
        return 1
    return 0


def _ranch_layout(index: int, workspace_id: str, snap: dict) -> None:
    """Ranch name, boundary file and any property grouping in it (no coordinates)."""
    from ranch_ai.rancher.worker import workspace_inputs

    try:
        _settings, pastures, boundary = workspace_inputs(workspace_id)
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        print(f"   layout: could not read boundary ({type(exc).__name__})"); return
    print(f"   ranch name: {(snap.get('ranch') or {}).get('name')!r}, boundary file: {boundary!r}, "
          f"{(snap.get('ranch') or {}).get('acres')} acres")
    if pastures is None:
        return
    cols = [c for c in pastures.columns if c != "geometry"]
    print(f"   boundary columns: {cols}")
    for col in cols:
        if any(word in col.lower() for word in ("ranch", "property", "unit", "group", "folder", "parent", "owner")):
            values = sorted({str(v) for v in pastures[col].dropna().tolist()})[:12]
            print(f"   {col}: {values}")


def summary() -> int:
    """Per-ranch health from stored snapshots, with no names, emails or locations (safe for public CI logs)."""
    from datetime import datetime, timezone

    from ranch_ai.rancher.worker import account_workspaces

    store = AppStore()
    workspaces = account_workspaces(default_settings.auth_db_path)
    print(f"{len(workspaces)} account(s)")
    for index, workspace_id in enumerate(workspaces, start=1):
        snap = store.latest_snapshot(workspace_id)
        if snap is None:
            print(f"ranch {index}: no snapshot yet"); continue
        if snap.get("setup_needed"):
            print(f"ranch {index}: no pasture boundary uploaded"); continue
        age_h = None
        try:
            age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(snap["generated_at"])).total_seconds() / 3600
        except (KeyError, ValueError):
            pass
        sources = snap.get("sources", [])
        live = [x["name"] for x in sources if x.get("live")]
        down = [x for x in sources if not x.get("live")]
        terrain = store.terrain_meta(workspace_id)
        _ranch_layout(index, workspace_id, snap)
        age = f"{age_h:.1f} h ago" if age_h is not None else "at an unknown time"
        print(f"ranch {index}: {len(snap.get('pastures', []))} pastures, status {snap.get('counts')}, "
              f"{len(live)}/{len(sources)} sources live, updated {age}")
        for x in down:
            print(f"   NOT LIVE: {x['name']}" + (f" - {x['note']}" if x.get("note") else ""))
        # What is driving the status: how many pastures each signal puts at each level, with one example.
        tally: dict[tuple[str, str], list] = {}
        for p in snap.get("pastures", []):
            for g in p.get("signals", []):
                tally.setdefault((g.get("label", g.get("key")), g.get("level")), []).append(g.get("text", ""))
        for (label, level), texts in sorted(tally.items()):
            print(f"   signal {label}: {level} x{len(texts)} (e.g. {texts[0][:110]})")
        water = snap.get("water_map") or {}
        if water:
            kinds: dict[str, int] = {}
            for f in water.get("features", []):
                kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
            print(f"   USGS water map: {len(water.get('features', []))} features {kinds}" + (f" ({water['error']})" if water.get("error") else ""))
        shapes = store.list_shapes(workspace_id)
        if shapes:
            kinds: dict[str, int] = {}
            for s in shapes:
                kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
            last = max(str(s.get("updated_at") or "") for s in shapes)
            print(f"   drawn in the app: {kinds}, last change {last[:16]}")
        if terrain:
            print(f"   3D: {terrain['nx']}x{terrain['ny']} mesh, DEM {terrain['dem_source']} {terrain['dem_resolution_m']} m, "
                  f"surface {terrain['texture_source']}" + (f" ({terrain['texture_note']})" if terrain.get("texture_note") else ""))
            try:
                from ranch_ai.rancher.worker import drawn_pastures, outline_hash
                drawn = drawn_pastures(workspace_id, store)
                match = "n/a (uses the uploaded file)" if drawn is None else ("yes" if terrain.get("outline_hash") == outline_hash(drawn) else "NO, waiting for a rebuild")
                print(f"   3D built {str(terrain.get('updated_at'))[:16]}, outlines match the current pastures: {match}")
            except Exception as exc:  # noqa: BLE001 - diagnostics only
                print(f"   3D outline check failed: {type(exc).__name__}")
    return 0


def diagnose_ranch_greenness(workspace_id: str) -> int:
    """Ranch-wide Sentinel-2 pull, step by step: search, one scene read, progress so far (no locations printed)."""
    import time as _time
    from datetime import date

    from ranch_ai.rancher.worker import usable_providers, workspace_inputs
    from ranch_ai.vegetation.ranch_ndvi import (
        RanchNDVIStore, _bbox, greenness_anomalies, pasture_geometries, scene_pasture_ndvi, search_scenes, thin_scenes)

    app_settings, pastures, _ = workspace_inputs(workspace_id)
    switched = usable_providers(app_settings)
    print(f"greenness source: {app_settings.public_data.vegetation.provider}" + (f" ({switched[0]})" if switched else ""))
    geoms = pasture_geometries(pastures)
    today = date.today()
    t0 = _time.monotonic()
    try:
        items = search_scenes(_bbox(geoms.values()), date(today.year - 4, today.month, 1), today)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL search: {type(exc).__name__}: {str(exc)[:200]}"); return 1
    kept = thin_scenes(items)
    print(f"ok   search: {len(items)} scenes under 30% cloud in 4 years, {len(kept)} kept (2 clearest per month per tile), "
          f"{_time.monotonic() - t0:.1f}s")
    if kept:
        t0 = _time.monotonic()
        try:
            values = scene_pasture_ndvi(kept[0], geoms)
            print(f"ok   newest scene {kept[0]['properties'].get('datetime', '')[:10]}: {len(values)}/{len(geoms)} pastures clear, "
                  f"read in {_time.monotonic() - t0:.1f}s (one read per band for the whole ranch)")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL scene read: {type(exc).__name__}: {str(exc)[:200]}"); return 1
    store = RanchNDVIStore(default_settings.vegetation_cache_dir / "ranch_ndvi.sqlite")
    states = store.scene_states(workspace_id)
    done = sum(1 for st in states.values() if st["status"] in {"done", "empty"})
    errors = [st["note"] for st in states.values() if st["status"] == "error"]
    anomalies = greenness_anomalies(store.history(workspace_id), today)
    have = sum(1 for a in anomalies.values() if a.get("anomaly_pct") is not None)
    print(f"progress: {done} scenes stored, {len(errors)} with errors" + (f" (e.g. {errors[0][:120]})" if errors else "")
          + f"; greenness vs. normal ready for {have}/{len(geoms)} pastures")
    return 0


def diagnose_all(redact: bool = True) -> int:
    from ranch_ai.rancher.worker import account_workspaces, workspace_inputs

    worst = 0
    for index, workspace_id in enumerate(account_workspaces(default_settings.auth_db_path), start=1):
        if workspace_inputs(workspace_id)[1] is None:
            continue
        print(f"--- ranch {index}")
        worst = max(worst, diagnose_ranch_greenness(workspace_id))
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RangeIQ admin: run one account's ranch.")
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("find", help="Show an account's ranch and boundary.")
    f.add_argument("email")
    b = sub.add_parser("build", help="Pull live data and build the phone-app snapshot + 3D terrain now.")
    b.add_argument("email")
    b.add_argument("--force-live", action="store_true", help="Use free live sources even where the account chose 'mock'.")
    b.add_argument("--export", type=Path, help="Also write the DEM GeoTIFF, terrain CSV, aerial photo and snapshot here.")
    b.add_argument("--db", help="App database path.")
    d = sub.add_parser("diagnose", help="Test the satellite greenness pull step by step for an account.")
    d.add_argument("email")
    sub.add_parser("summary", help="Per-ranch health with no personal details (safe for public logs).")
    sub.add_parser("diagnose-all", help="Greenness diagnosis for every ranch, with no personal details.")
    args = parser.parse_args(argv)
    if args.command == "summary":
        return summary()
    if args.command == "diagnose-all":
        return diagnose_all(redact=True)

    user = find_account(args.email)
    if args.command == "diagnose":
        return diagnose_greenness(normalize_workspace_id(user.workspace_id))
    info = describe(user)
    print(json.dumps(info, indent=2))
    if args.command == "find":
        if not info.get("boundary_file"):
            print("\nNo pasture boundary uploaded for this account yet: sign in as them on the website and upload a KML/KMZ/GeoJSON.")
        return 0

    from ranch_ai.rancher.worker import build_workspace

    store = AppStore(args.db)
    print("\nPulling live data (a first lidar + aerial pull can take a few minutes)...", flush=True)
    report = build_workspace(info["workspace_id"], store=store, force_live=args.force_live)
    print(json.dumps(report, indent=2))
    if args.export and report.get("status") == "ok":
        for path in export(info["workspace_id"], store, args.export):
            print("wrote", path)
    missing = [name for name, state in report.get("sources", {}).items() if state != "live"]
    if missing:
        print("\nNot live:", ", ".join(missing), "- check the server's internet access and the worker log.", file=sys.stderr)
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
