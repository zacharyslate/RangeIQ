from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from ranch_ai.config import Settings, save_settings_file, settings
from ranch_ai.pipeline import MvpArtifacts, run_mvp_pipeline
from ranch_ai.services.auth_service import AuthService, AuthUser


BUNDLE_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_file(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _copy_model_artifacts(source_dir: Path, destination_dir: Path) -> list[str]:
    copied: list[str] = []
    destination_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("forage_model.pkl", "stress_model.pkl", "metadata.json"):
        source_path = source_dir / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Expected model artifact was missing: {source_path}")
        shutil.copy2(source_path, destination_dir / filename)
        copied.append(filename)
    return copied


def _portable_relative_path(path: Path, *, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _bundle_path(bundle_root: Path, relative_value: str | Path) -> Path:
    text = str(relative_value).strip()
    if not text:
        return bundle_root
    return bundle_root / Path(text.replace("\\", "/"))


def _sync_owner_from_reference(path: Path, reference: Path) -> None:
    if os.name == "nt" or not path.exists() or not reference.exists():
        return

    reference_stat = reference.stat()
    targets = [path]
    if path.is_dir():
        targets.extend(sorted(path.rglob("*")))

    for target in targets:
        try:
            os.chown(target, reference_stat.st_uid, reference_stat.st_gid)
        except OSError:
            continue


def _build_runtime_settings_for_manifest(base_settings: Settings, manifest: dict[str, Any]) -> Settings:
    runtime_settings = copy.deepcopy(base_settings)
    ranch_payload = manifest.get("ranch", {})
    providers_payload = manifest.get("providers", {})
    refresh_payload = manifest.get("refresh_hours", {})

    runtime_settings.ranch.name = str(ranch_payload.get("name", runtime_settings.ranch.name))
    runtime_settings.ranch.address = str(ranch_payload.get("address", runtime_settings.ranch.address))
    runtime_settings.ranch.latitude = float(ranch_payload.get("latitude", runtime_settings.ranch.latitude))
    runtime_settings.ranch.longitude = float(ranch_payload.get("longitude", runtime_settings.ranch.longitude))
    runtime_settings.ranch.timezone = str(ranch_payload.get("timezone", runtime_settings.ranch.timezone))
    runtime_settings.ranch.units = str(ranch_payload.get("units", runtime_settings.ranch.units))

    runtime_settings.weather.provider = str(providers_payload.get("weather", runtime_settings.weather.provider))
    runtime_settings.alerts.provider = str(providers_payload.get("alerts", runtime_settings.alerts.provider))
    runtime_settings.public_data.cache_enabled = bool(
        providers_payload.get("public_cache_enabled", runtime_settings.public_data.cache_enabled)
    )
    runtime_settings.public_data.historical_weather.provider = str(
        providers_payload.get("historical_weather", runtime_settings.public_data.historical_weather.provider)
    )
    runtime_settings.public_data.soils.provider = str(
        providers_payload.get("soils", runtime_settings.public_data.soils.provider)
    )
    runtime_settings.public_data.drought.provider = str(
        providers_payload.get("drought", runtime_settings.public_data.drought.provider)
    )
    runtime_settings.public_data.vegetation.provider = str(
        providers_payload.get("vegetation", runtime_settings.public_data.vegetation.provider)
    )

    runtime_settings.public_data.historical_weather.refresh_hours = int(
        refresh_payload.get("historical_weather", runtime_settings.public_data.historical_weather.refresh_hours)
    )
    runtime_settings.public_data.soils.refresh_hours = int(
        refresh_payload.get("soils", runtime_settings.public_data.soils.refresh_hours)
    )
    runtime_settings.public_data.drought.refresh_hours = int(
        refresh_payload.get("drought", runtime_settings.public_data.drought.refresh_hours)
    )
    runtime_settings.public_data.vegetation.refresh_hours = int(
        refresh_payload.get("vegetation", runtime_settings.public_data.vegetation.refresh_hours)
    )
    runtime_settings.training.use_sensor_data = False
    runtime_settings.sensor_network.enabled = False
    runtime_settings.sensor_network.mode = "under_development"
    runtime_settings.sensors.provider = "under_development"
    return runtime_settings


def _build_workspace_session_state(runtime_settings: Settings, manifest: dict[str, Any]) -> dict[str, Any]:
    scenario_payload = manifest.get("scenario", {})
    appearance_payload = manifest.get("appearance", {})
    return {
        "theme_mode": str(appearance_payload.get("theme_mode", "High Plains Day")),
        "weeks": int(scenario_payload.get("weeks", runtime_settings.default_weeks)),
        "history_years": int(scenario_payload.get("history_years", runtime_settings.default_history_years)),
        "seed": int(scenario_payload.get("seed", runtime_settings.random_seed)),
        "ranch_name": runtime_settings.ranch.name,
        "ranch_address": runtime_settings.ranch.address,
        "ranch_lat": runtime_settings.ranch.latitude,
        "ranch_lon": runtime_settings.ranch.longitude,
        "ranch_timezone": runtime_settings.ranch.timezone,
        "ranch_units": runtime_settings.ranch.units,
        "map_basemap": str(appearance_payload.get("map_basemap", "naip")),
        "weather_provider": runtime_settings.weather.provider,
        "alerts_provider": runtime_settings.alerts.provider,
        "sensor_provider": runtime_settings.sensors.provider,
        "historical_weather_provider": runtime_settings.public_data.historical_weather.provider,
        "soils_provider": runtime_settings.public_data.soils.provider,
        "drought_provider": runtime_settings.public_data.drought.provider,
        "vegetation_provider": runtime_settings.public_data.vegetation.provider,
        "public_cache_enabled": runtime_settings.public_data.cache_enabled,
        "historical_weather_refresh_hours": runtime_settings.public_data.historical_weather.refresh_hours,
        "soils_refresh_hours": runtime_settings.public_data.soils.refresh_hours,
        "drought_refresh_hours": runtime_settings.public_data.drought.refresh_hours,
        "vegetation_refresh_hours": runtime_settings.public_data.vegetation.refresh_hours,
        "sensor_network_mode": runtime_settings.sensor_network.mode,
        "sensor_network_packet_limit": runtime_settings.sensor_network.packet_limit,
        "expected_interval_minutes": runtime_settings.sensors.expected_interval_minutes,
        "stale_after_minutes": runtime_settings.sensors.stale_after_minutes,
        "offline_after_minutes": runtime_settings.sensors.offline_after_minutes,
        "low_battery_voltage": runtime_settings.sensors.low_battery_voltage,
        "low_signal_threshold": runtime_settings.sensors.low_signal_threshold,
        "network_low_signal_rssi": runtime_settings.thresholds.low_signal_rssi,
        "network_low_water_tank_pct": runtime_settings.thresholds.low_water_tank_pct,
        "high_wind_mph": runtime_settings.fire_risk.high_wind_mph,
        "high_gust_mph": runtime_settings.fire_risk.high_gust_mph,
        "low_humidity_pct": runtime_settings.fire_risk.low_humidity_pct,
        "high_temperature_f": runtime_settings.fire_risk.high_temperature_f,
        "low_rainfall_7d_in": runtime_settings.fire_risk.low_rainfall_7d_in,
        "low_soil_moisture_pct": runtime_settings.fire_risk.low_soil_moisture_pct,
    }


def _write_workspace_state(
    *,
    runtime_settings: Settings,
    workspace_id: str,
    session_state: dict[str, Any],
    saved_boundary_filename: str,
    saved_boundary_path: Path,
) -> Path:
    payload = {
        "workspace_id": workspace_id,
        "saved_at": _utc_now_iso(),
        "config_path": str(runtime_settings.workspace_config_path_for(workspace_id)),
        "session_state": session_state,
        "saved_boundary": {
            "filename": saved_boundary_filename,
            "path": str(saved_boundary_path),
        },
    }
    state_path = runtime_settings.workspace_state_path_for(workspace_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return state_path


def create_pretrained_workspace_bundle(
    *,
    email: str,
    ranch_name: str,
    ranch_address: str,
    ranch_latitude: float,
    ranch_longitude: float,
    boundary_path: str | Path,
    bundle_dir: str | Path,
    weeks: int = 26,
    history_years: int = 10,
    seed: int = 42,
    theme_mode: str = "High Plains Day",
    map_basemap: str = "naip",
    app_settings: Settings = settings,
    cleanup_temp_workspace: bool = True,
) -> dict[str, Any]:
    boundary_source = Path(boundary_path)
    if not boundary_source.exists():
        raise FileNotFoundError(f"Boundary file was not found: {boundary_source}")

    bundle_root = Path(bundle_dir)
    models_dir = bundle_root / "models"
    boundary_dir = bundle_root / "boundary"
    reports_dir = bundle_root / "reports"
    bundle_root.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    boundary_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    temporary_workspace_id = f"bundle-{uuid4().hex[:10]}"
    artifacts: MvpArtifacts = run_mvp_pipeline(
        pasture_path=boundary_source,
        weeks=weeks,
        history_years=history_years,
        seed=seed,
        write_outputs=False,
        app_settings=app_settings,
        workspace_id=temporary_workspace_id,
    )

    temporary_model_dir = app_settings.workspace_model_dir_for(temporary_workspace_id)
    copied_models = _copy_model_artifacts(temporary_model_dir, models_dir)
    copied_boundary = _copy_file(boundary_source, boundary_dir / boundary_source.name)

    latest_snapshot_path = reports_dir / "latest_snapshot.csv"
    monthly_report_csv_path = reports_dir / "monthly_report.csv"
    monthly_report_md_path = reports_dir / "monthly_report.md"
    artifacts.latest_snapshot.to_csv(latest_snapshot_path, index=False)
    artifacts.monthly_report_table.to_csv(monthly_report_csv_path, index=False)
    monthly_report_md_path.write_text(artifacts.monthly_report_markdown, encoding="utf-8")

    manifest = {
        "version": BUNDLE_VERSION,
        "created_at": _utc_now_iso(),
        "email": email.strip().lower(),
        "ranch": {
            "name": ranch_name,
            "address": ranch_address,
            "latitude": float(ranch_latitude),
            "longitude": float(ranch_longitude),
            "timezone": app_settings.ranch.timezone,
            "units": app_settings.ranch.units,
        },
        "appearance": {
            "theme_mode": theme_mode,
            "map_basemap": map_basemap,
        },
        "scenario": {
            "weeks": int(weeks),
            "history_years": int(history_years),
            "seed": int(seed),
        },
        "providers": {
            "weather": app_settings.weather.provider,
            "alerts": app_settings.alerts.provider,
            "historical_weather": app_settings.public_data.historical_weather.provider,
            "soils": app_settings.public_data.soils.provider,
            "drought": app_settings.public_data.drought.provider,
            "vegetation": app_settings.public_data.vegetation.provider,
            "public_cache_enabled": app_settings.public_data.cache_enabled,
        },
        "refresh_hours": {
            "historical_weather": app_settings.public_data.historical_weather.refresh_hours,
            "soils": app_settings.public_data.soils.refresh_hours,
            "drought": app_settings.public_data.drought.refresh_hours,
            "vegetation": app_settings.public_data.vegetation.refresh_hours,
        },
        "boundary": {
            "filename": copied_boundary.name,
            "relative_path": _portable_relative_path(copied_boundary, root=bundle_root),
        },
        "models": {
            "relative_dir": _portable_relative_path(models_dir, root=bundle_root),
            "files": copied_models,
        },
        "reports": {
            "latest_snapshot_csv": _portable_relative_path(latest_snapshot_path, root=bundle_root),
            "monthly_report_csv": _portable_relative_path(monthly_report_csv_path, root=bundle_root),
            "monthly_report_md": _portable_relative_path(monthly_report_md_path, root=bundle_root),
        },
        "training": {
            "pasture_count": int(len(artifacts.pastures)),
            "weekly_row_count": int(len(artifacts.weekly_data)),
            "selected_forage_model": artifacts.selected_forage_model,
            "model_metrics": artifacts.model_metrics,
            "training_dataset_summary": artifacts.training_dataset_summary,
            "model_storage_summary": artifacts.model_storage_summary,
        },
    }
    manifest_path = bundle_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if cleanup_temp_workspace:
        temporary_workspace_root = app_settings.workspace_user_data_root / temporary_workspace_id
        if temporary_workspace_root.exists():
            shutil.rmtree(temporary_workspace_root, ignore_errors=True)

    return {
        "bundle_dir": str(bundle_root),
        "manifest_path": str(manifest_path),
        "boundary_path": str(copied_boundary),
        "model_dir": str(models_dir),
        "latest_snapshot_path": str(latest_snapshot_path),
        "monthly_report_csv_path": str(monthly_report_csv_path),
        "monthly_report_md_path": str(monthly_report_md_path),
        "training": manifest["training"],
    }


def apply_pretrained_workspace_bundle(
    *,
    bundle_dir: str | Path,
    email: str | None = None,
    app_settings: Settings = settings,
) -> dict[str, Any]:
    bundle_root = Path(bundle_dir)
    manifest_path = bundle_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Bundle manifest was not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_email = str(email or manifest.get("email", "")).strip().lower()
    if not target_email:
        raise ValueError("A target email is required to apply a workspace bundle.")

    auth_service = AuthService(app_settings.auth_db_path)
    target_user = auth_service.get_user_by_email(target_email)
    if target_user is None:
        raise ValueError(f"No RangeIQ account exists for {target_email}.")

    ranch_payload = manifest.get("ranch", {})
    updated_user: AuthUser = auth_service.update_user_profile(
        target_user.user_id,
        ranch_name=str(ranch_payload.get("name", target_user.ranch_name)),
        ranch_address=str(ranch_payload.get("address", target_user.ranch_address)),
        ranch_latitude=float(ranch_payload.get("latitude", target_user.ranch_latitude or 0.0)),
        ranch_longitude=float(ranch_payload.get("longitude", target_user.ranch_longitude or 0.0)),
    )
    workspace_id = updated_user.workspace_id

    boundary_payload = manifest.get("boundary", {})
    boundary_source = _bundle_path(bundle_root, boundary_payload.get("relative_path", ""))
    if not boundary_source.exists():
        raise FileNotFoundError(f"Bundle boundary file was not found: {boundary_source}")
    boundary_suffix = boundary_source.suffix.lower() or ".geojson"
    boundary_destination_dir = app_settings.workspace_boundary_dir_for(workspace_id)
    boundary_destination = boundary_destination_dir / f"saved_boundary{boundary_suffix}"
    boundary_destination_dir.mkdir(parents=True, exist_ok=True)
    for existing in boundary_destination_dir.glob("saved_boundary.*"):
        if existing.is_file():
            existing.unlink(missing_ok=True)
    shutil.copy2(boundary_source, boundary_destination)
    _sync_owner_from_reference(boundary_destination_dir, app_settings.workspace_user_data_root)

    models_payload = manifest.get("models", {})
    model_source_dir = _bundle_path(bundle_root, models_payload.get("relative_dir", "models"))
    copied_models = _copy_model_artifacts(model_source_dir, app_settings.workspace_model_dir_for(workspace_id))
    _sync_owner_from_reference(app_settings.workspace_model_dir_for(workspace_id), app_settings.workspace_user_data_root)

    runtime_settings = _build_runtime_settings_for_manifest(app_settings, manifest)
    config_path = save_settings_file(runtime_settings, path=runtime_settings.workspace_config_path_for(workspace_id))
    session_state = _build_workspace_session_state(runtime_settings, manifest)
    state_path = _write_workspace_state(
        runtime_settings=runtime_settings,
        workspace_id=workspace_id,
        session_state=session_state,
        saved_boundary_filename=boundary_source.name,
        saved_boundary_path=boundary_destination,
    )
    _sync_owner_from_reference(config_path.parent, app_settings.workspace_profile_root)

    return {
        "email": updated_user.email,
        "workspace_id": workspace_id,
        "config_path": str(config_path),
        "state_path": str(state_path),
        "boundary_path": str(boundary_destination),
        "model_dir": str(app_settings.workspace_model_dir_for(workspace_id)),
        "copied_models": copied_models,
    }
