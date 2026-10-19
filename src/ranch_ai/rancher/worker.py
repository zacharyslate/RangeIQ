"""Nightly worker: build each ranch's phone-app snapshot and store it.

    python -m ranch_ai.rancher.worker                 # every account's ranch
    python -m ranch_ai.rancher.worker --workspace ID  # one ranch
    python -m ranch_ai.rancher.worker --demo          # labeled sample data when sources are down

Run it from a systemd timer (see deploy/systemd/rangeiq-worker.*.example).
All the slow and memory-hungry work (network pulls, rasters, pandas) happens
here, never while a rancher is waiting on the phone.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from ranch_ai.config import Settings, load_settings, normalize_workspace_id, settings as default_settings
from ranch_ai.rancher.store import AppStore
from ranch_ai.utils.io import load_pastures

DEFAULT_WORKSPACE = "default"


def account_workspaces(auth_db_path: Path, store: AppStore | None = None) -> list[str]:
    """Owners' ranches. Crew members (ranch hands) work on their owner's ranch, so their own empty one is skipped."""
    if not Path(auth_db_path).exists():
        return []
    crew = (store or AppStore()).crew_user_ids()
    with sqlite3.connect(auth_db_path) as conn:
        try:
            rows = conn.execute("SELECT user_id, workspace_id FROM users ORDER BY created_at").fetchall()
        except sqlite3.Error:
            return []
    return [normalize_workspace_id(ws) for uid, ws in rows if ws and uid not in crew]


LIVE_DEFAULTS = {
    "weather": "nws",
    "alerts": "nws",
    "historical_weather": "nasa_power",
    "soils": "usda_sda",
    "drought": "usdm",
    "vegetation": "earth_search_stac",
}


def force_live_providers(app_settings: Settings) -> list[str]:
    """Switch any provider an account left on 'mock' to the free live source. Returns what changed."""
    changed = []
    if str(app_settings.weather.provider).lower() == "mock":
        app_settings.weather.provider = LIVE_DEFAULTS["weather"]; changed.append("weather")
    if str(app_settings.alerts.provider).lower() == "mock":
        app_settings.alerts.provider = LIVE_DEFAULTS["alerts"]; changed.append("alerts")
    for name in ("historical_weather", "soils", "drought", "vegetation"):
        cfg = getattr(app_settings.public_data, name)
        if str(cfg.provider).lower() == "mock":
            cfg.provider = LIVE_DEFAULTS[name]; changed.append(name)
    if str(app_settings.terrain.provider).lower() == "mock":
        app_settings.terrain.provider = "usgs_3dep"; changed.append("terrain")
    return changed


def usable_providers(app_settings: Settings, env: dict | None = None) -> list[str]:
    """If an account picked a greenness source that needs a key this server doesn't have, use the free
    Earth Search copy of the same Sentinel-2 imagery instead of silently falling back to demo numbers.
    A source that has its key is left alone. Returns notes on what was switched."""
    env = os.environ if env is None else env
    veg = app_settings.public_data.vegetation
    provider = str(veg.provider).lower()
    missing = {
        "climate_engine": not env.get(veg.climate_engine_api_key_env),
        "appeears": not (env.get(veg.appeears_username_env) and env.get(veg.appeears_password_env)),
    }
    if missing.get(provider):
        veg.provider = LIVE_DEFAULTS["vegetation"]
        return [f"vegetation: {provider} has no key on this server, using earth_search_stac (same Sentinel-2 imagery)"]
    return []


def terrain_needs_rebuild(store: AppStore, workspace_id: str, pastures, max_age_days: int = 30) -> bool:
    """The 3D terrain and aerial photo change rarely: rebuild when the format, the boundary or the month changes."""
    from datetime import datetime, timezone

    from ranch_ai.rancher.terrain3d import ASSET_VERSION

    meta = store.terrain_meta(workspace_id)
    if not meta or meta.get("asset_version") != ASSET_VERSION:
        return True
    ids = sorted(str(p) for p in pastures["pasture_id"])
    if sorted(str(o.get("id")) for o in meta.get("outlines", [])) != ids:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(str(meta.get("updated_at")).replace("Z", "+00:00"))
    except ValueError:
        return True
    return age.days >= max_age_days


def ranch_greenness(workspace_id: str, pastures, *, budget_seconds: float | None = None, store=None) -> dict:
    """Read new Sentinel-2 scenes for the whole ranch (time-limited), then work out each pasture's greenness."""
    from datetime import date

    from ranch_ai.vegetation.ranch_ndvi import RanchNDVIStore, greenness_anomalies, update_ranch_ndvi

    store = store or RanchNDVIStore(default_settings.vegetation_cache_dir / "ranch_ndvi.sqlite")
    budget = float(budget_seconds if budget_seconds is not None else os.getenv("RANGEIQ_NDVI_BUDGET_SECONDS", "300"))
    try:
        rep = update_ranch_ndvi(store, workspace_id, pastures, budget_seconds=budget)
    except Exception as exc:  # noqa: BLE001 - greenness must never stop the weather update
        return {"anomalies": {}, "error": f"Satellite greenness update failed: {type(exc).__name__}", "report": str(exc)[:200]}
    anomalies = greenness_anomalies(store.history(workspace_id), date.today())
    note = None
    if rep.scenes_left:
        note = f"Still loading satellite history: {rep.scenes_found - rep.scenes_left} of {rep.scenes_found} scenes so far."
    return {"anomalies": anomalies, "note": note, "error": rep.error, "report": rep.text()}


def workspace_inputs(workspace_id: str, base: Settings = default_settings):
    """Settings + pasture boundaries for a workspace, as saved from the desktop console.

    Returns (settings, pastures or None, boundary_label). Real accounts with no
    uploaded boundary get None: we never show them someone else's sample ranch.
    """
    config_path = base.workspace_config_path_for(workspace_id)
    app_settings = load_settings(config_path) if config_path.exists() else load_settings()
    state_path = base.workspace_state_path_for(workspace_id)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            info = state.get("saved_boundary") or {}
            path, name = info.get("path"), info.get("filename")
            if path and name and Path(path).exists():
                return app_settings, load_pastures(uploaded_name=name, uploaded_bytes=Path(path).read_bytes()), str(name)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if workspace_id in {DEFAULT_WORKSPACE, "demo"}:
        return app_settings, load_pastures(app_settings.default_pasture_path), "sample ranch"
    return app_settings, None, None


def build_workspace(
    workspace_id: str,
    *,
    store: AppStore,
    demo: bool = False,
    include_terrain: bool = True,
    force_live: bool = False,
) -> dict:
    """Build and store one ranch's snapshot (and 3D terrain). Returns a short report."""
    from ranch_ai.rancher.snapshot import build_snapshot, is_live

    app_settings, pastures, boundary = workspace_inputs(workspace_id)
    report: dict = {"workspace_id": workspace_id, "boundary": boundary}
    switched = usable_providers(app_settings)
    if switched:
        report["switched"] = switched
    if force_live:
        report["forced_live"] = force_live_providers(app_settings)
    if pastures is None:
        store.save_snapshot(workspace_id, {
            "version": 1,
            "setup_needed": True,
            "message": "Upload your pasture boundary on the RangeIQ website (Settings > Scenario & Boundary), then check back after the next update.",
        })
        report["status"] = "no boundary uploaded"
        return report

    terrain_result = None
    if include_terrain:
        from ranch_ai.terrain import TerrainService

        terrain_result = TerrainService(app_settings).load(pastures)
        report["terrain"] = {k: terrain_result.status.get(k) for k in ("mode", "resolution_m", "width_px", "height_px", "error")}

    greenness = None
    if not demo and str(app_settings.public_data.vegetation.provider).lower() == "earth_search_stac":
        greenness = ranch_greenness(workspace_id, pastures)
        report["greenness"] = greenness.get("report")

    snapshot = build_snapshot(
        app_settings,
        pastures,
        greenness=greenness,
        logs=store.list_logs(workspace_id, limit=1000),
        photos=store.list_photos(workspace_id, limit=500),
        demo=demo,
        include_terrain=include_terrain,
        terrain_result=terrain_result,
    )
    if not demo:
        from ranch_ai.rancher.water_map import water_features

        water = water_features(workspace_id, pastures, default_settings.vegetation_cache_dir.parent / "water")
        snapshot["water_map"] = water
        snapshot.setdefault("sources", []).append({
            "name": "USGS water map (NHD)", "provider": "USGS National Hydrography Dataset", "live": not water.get("error") or bool(water["features"]),
            "stale": False, "demo": False, "as_of": water.get("as_of"), "mode": "real" if not water.get("error") else "unavailable",
            "note": water.get("error")})
        report["water_features"] = len(water["features"])
    store.save_snapshot(workspace_id, snapshot)
    report["pastures"] = len(snapshot["pastures"])
    report["acres"] = snapshot["ranch"]["acres"]
    report["sources"] = {s["name"]: ("live" if s.get("live") else "demo" if s.get("demo") else "NOT AVAILABLE") for s in snapshot["sources"]}
    notes = {s["name"]: s["note"] for s in snapshot["sources"] if s.get("note")}
    if notes:
        report["why_not_live"] = notes

    if terrain_result is not None and terrain_result.grid is not None and (is_live(terrain_result.status.get("mode")) or demo) \
            and terrain_needs_rebuild(store, workspace_id, pastures):
        from ranch_ai.rancher.terrain3d import build_terrain_assets

        assets = build_terrain_assets(terrain_result.grid, pastures, user_agent=app_settings.terrain.user_agent)
        store.save_terrain(workspace_id, assets["meta"], assets["height"], assets["texture"], assets["texture_mime"])
        report["terrain_3d"] = {
            "mesh": f"{assets['meta']['nx']}x{assets['meta']['ny']} @ {assets['meta']['cell_m']:.1f} m",
            "texture": assets["meta"]["texture_source"],
            "texture_note": assets["meta"]["texture_note"],
            "bytes": len(assets["height"]) + len(assets["texture"]),
        }
    report["status"] = "ok"
    return report


def run(workspaces: list[str], *, store: AppStore, demo: bool = False, include_terrain: bool = True, force_live: bool = False) -> int:
    failures = 0
    for workspace_id in workspaces:
        started = time.time()
        try:
            report = build_workspace(workspace_id, store=store, demo=demo, include_terrain=include_terrain, force_live=force_live)
            sources = report.get("sources", {})
            live = sum(1 for v in sources.values() if v == "live")
            print(f"[rangeiq-worker] {workspace_id}: {report['status']}, {report.get('pastures', 0)} pastures, "
                  f"{live}/{len(sources)} sources live, {time.time() - started:.1f}s"
                  + (f"; {report['greenness']}" if report.get("greenness") else ""))
        except Exception as exc:  # noqa: BLE001 - one bad ranch must not stop the others
            failures += 1
            print(f"[rangeiq-worker] {workspace_id}: FAILED: {exc}", file=sys.stderr)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build RangeIQ phone-app snapshots.")
    parser.add_argument("--workspace", action="append", help="Workspace id (repeatable). Default: every account.")
    parser.add_argument("--demo", action="store_true", help="Allow labeled sample data when sources are unavailable.")
    parser.add_argument("--no-terrain", action="store_true", help="Skip the lidar terrain summary.")
    parser.add_argument("--force-live", action="store_true", help="Use free live sources even where an account chose 'mock'.")
    parser.add_argument("--db", help="App database path (default: data/processed/rangeiq_app.sqlite).")
    args = parser.parse_args(argv)

    store = AppStore(args.db)
    workspaces = [normalize_workspace_id(w) for w in args.workspace] if args.workspace else account_workspaces(default_settings.auth_db_path)
    if not workspaces:
        workspaces = [DEFAULT_WORKSPACE]
    failures = run(workspaces, store=store, demo=args.demo, include_terrain=not args.no_terrain, force_live=args.force_live)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
