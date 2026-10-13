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
    args = parser.parse_args(argv)

    user = find_account(args.email)
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
