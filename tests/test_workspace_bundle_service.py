from __future__ import annotations

import copy
import json
from pathlib import Path

from ranch_ai.config import settings
from ranch_ai.services.auth_service import AuthService
from ranch_ai.services.workspace_bundle_service import apply_pretrained_workspace_bundle


def _temp_settings(tmp_path: Path):
    temp_settings = copy.deepcopy(settings)
    temp_settings.project_root = tmp_path
    temp_settings.config_dir = tmp_path / "config"
    temp_settings.auth_db_path = tmp_path / "data" / "processed" / "rangeiq_auth.sqlite"
    temp_settings.workspace_profile_root = tmp_path / "config" / "workspaces"
    temp_settings.workspace_user_data_root = tmp_path / "data" / "user" / "workspaces"
    temp_settings.config_path = tmp_path / "config.yaml"
    temp_settings.user_data_dir = tmp_path / "data" / "user"
    return temp_settings


def test_apply_pretrained_workspace_bundle_updates_user_workspace(tmp_path: Path):
    temp_settings = _temp_settings(tmp_path)
    auth_service = AuthService(temp_settings.auth_db_path)
    user = auth_service.create_user(
        email="justinwarren1984@gmail.com",
        password="supersecure",
        full_name="Justin Warren",
        ranch_name="Original Ranch",
        ranch_address="Original Address",
    )

    bundle_dir = tmp_path / "bundle"
    (bundle_dir / "models").mkdir(parents=True)
    (bundle_dir / "boundary").mkdir(parents=True)
    boundary_path = bundle_dir / "boundary" / "clear-creek.kml"
    boundary_path.write_text("<kml>boundary</kml>", encoding="utf-8")
    (bundle_dir / "models" / "forage_model.pkl").write_bytes(b"forage")
    (bundle_dir / "models" / "stress_model.pkl").write_bytes(b"stress")
    (bundle_dir / "models" / "metadata.json").write_text('{"selected_forage_model": "GradientBoostingRegressor"}', encoding="utf-8")
    manifest = {
        "version": 1,
        "email": "justinwarren1984@gmail.com",
        "ranch": {
            "name": "Clear Creek Ranch",
            "address": "15650 private road 4107 baird, tx 79504",
            "latitude": 32.168316,
            "longitude": -99.470244,
            "timezone": "America/Chicago",
            "units": "imperial",
        },
        "appearance": {
            "theme_mode": "High Plains Day",
            "map_basemap": "naip",
        },
        "scenario": {
            "weeks": 26,
            "history_years": 10,
            "seed": 42,
        },
        "providers": {
            "weather": "openmeteo",
            "alerts": "nws",
            "historical_weather": "nasa_power",
            "soils": "usda_sda",
            "drought": "usdm",
            "vegetation": "earth_search_stac",
            "public_cache_enabled": True,
        },
        "refresh_hours": {
            "historical_weather": 168,
            "soils": 720,
            "drought": 48,
            "vegetation": 336,
        },
        "boundary": {
            "filename": "clear-creek.kml",
            "relative_path": "boundary/clear-creek.kml",
        },
        "models": {
            "relative_dir": "models",
            "files": ["forage_model.pkl", "stress_model.pkl", "metadata.json"],
        },
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = apply_pretrained_workspace_bundle(bundle_dir=bundle_dir, app_settings=temp_settings)

    updated = auth_service.get_user_by_id(user.user_id)
    assert updated is not None
    assert updated.ranch_name == "Clear Creek Ranch"
    assert updated.ranch_address == "15650 private road 4107 baird, tx 79504"
    assert updated.ranch_latitude == 32.168316
    assert updated.ranch_longitude == -99.470244
    assert result["workspace_id"] == user.workspace_id

    workspace_dir = temp_settings.workspace_user_data_root / user.workspace_id
    assert (workspace_dir / "saved_boundary.kml").exists()
    assert (workspace_dir / "models" / "forage_model.pkl").read_bytes() == b"forage"
    assert (workspace_dir / "models" / "stress_model.pkl").read_bytes() == b"stress"

    config_path = temp_settings.workspace_config_path_for(user.workspace_id)
    state_path = temp_settings.workspace_state_path_for(user.workspace_id)
    assert config_path.exists()
    assert state_path.exists()

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["session_state"]["ranch_name"] == "Clear Creek Ranch"
    assert state_payload["saved_boundary"]["filename"] == "clear-creek.kml"


def test_apply_pretrained_workspace_bundle_accepts_windows_style_relative_paths(tmp_path: Path):
    temp_settings = _temp_settings(tmp_path)
    auth_service = AuthService(temp_settings.auth_db_path)
    user = auth_service.create_user(
        email="justinwarren1984@gmail.com",
        password="supersecure",
        full_name="Justin Warren",
        ranch_name="Original Ranch",
        ranch_address="Original Address",
    )

    bundle_dir = tmp_path / "bundle"
    (bundle_dir / "models").mkdir(parents=True)
    (bundle_dir / "boundary").mkdir(parents=True)
    boundary_path = bundle_dir / "boundary" / "clear-creek.kml"
    boundary_path.write_text("<kml>boundary</kml>", encoding="utf-8")
    (bundle_dir / "models" / "forage_model.pkl").write_bytes(b"forage")
    (bundle_dir / "models" / "stress_model.pkl").write_bytes(b"stress")
    (bundle_dir / "models" / "metadata.json").write_text('{"selected_forage_model": "GradientBoostingRegressor"}', encoding="utf-8")
    manifest = {
        "version": 1,
        "email": "justinwarren1984@gmail.com",
        "ranch": {
            "name": "Clear Creek Ranch",
            "address": "15650 private road 4107 baird, tx 79504",
            "latitude": 32.168316,
            "longitude": -99.470244,
            "timezone": "America/Chicago",
            "units": "imperial",
        },
        "appearance": {
            "theme_mode": "High Plains Day",
            "map_basemap": "naip",
        },
        "scenario": {
            "weeks": 26,
            "history_years": 10,
            "seed": 42,
        },
        "providers": {
            "weather": "openmeteo",
            "alerts": "nws",
            "historical_weather": "nasa_power",
            "soils": "usda_sda",
            "drought": "usdm",
            "vegetation": "earth_search_stac",
            "public_cache_enabled": True,
        },
        "refresh_hours": {
            "historical_weather": 168,
            "soils": 720,
            "drought": 48,
            "vegetation": 336,
        },
        "boundary": {
            "filename": "clear-creek.kml",
            "relative_path": "boundary\\clear-creek.kml",
        },
        "models": {
            "relative_dir": "models",
            "files": ["forage_model.pkl", "stress_model.pkl", "metadata.json"],
        },
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = apply_pretrained_workspace_bundle(bundle_dir=bundle_dir, app_settings=temp_settings)

    assert result["workspace_id"] == user.workspace_id
    workspace_dir = temp_settings.workspace_user_data_root / user.workspace_id
    assert (workspace_dir / "saved_boundary.kml").exists()
