import copy

from ranch_ai.config import Settings, load_settings, normalize_workspace_id, save_settings_file, settings, settings_to_config_payload


def test_settings_to_config_payload_uses_relative_project_paths():
    runtime_settings = copy.deepcopy(settings)
    payload = settings_to_config_payload(runtime_settings)

    assert "project_root" not in payload
    assert payload["sensors"]["csv_path"].startswith("data/")
    assert payload["sensor_network"]["sqlite_path"].startswith("data/")


def test_save_settings_file_round_trips_config_values(tmp_path):
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.ranch.name = "Saved Ranch"
    runtime_settings.ranch.address = "123 Ranch Road"
    runtime_settings.public_data.vegetation.provider = "earth_search_stac"
    runtime_settings.sensors.csv_path = str(runtime_settings.project_root / "data" / "sensors" / "sensor_readings.csv")

    config_path = tmp_path / "config.yaml"
    save_settings_file(runtime_settings, path=config_path)
    reloaded = load_settings(config_path)

    assert reloaded.ranch.name == "Saved Ranch"
    assert reloaded.ranch.address == "123 Ranch Road"
    assert reloaded.public_data.vegetation.provider == "earth_search_stac"


def test_default_settings_prefer_real_public_providers(tmp_path):
    loaded = load_settings(tmp_path / "missing-config.yaml")

    assert loaded.weather.provider == "openmeteo"
    assert loaded.alerts.provider == "nws"
    assert loaded.public_data.historical_weather.provider == "nasa_power"
    assert loaded.public_data.soils.provider == "usda_sda"
    assert loaded.public_data.drought.provider == "usdm"
    assert loaded.public_data.vegetation.provider == "earth_search_stac"
    assert loaded.training.use_sensor_data is False
    assert loaded.sensor_network.enabled is False
    assert loaded.sensor_network.mode == "under_development"


def test_normalize_workspace_id_and_paths():
    normalized = normalize_workspace_id(" Caja Caliente Team 01 ")
    app_settings = Settings()

    assert normalized == "caja-caliente-team-01"
    assert app_settings.workspace_state_path_for(normalized).as_posix().endswith(
        "config/workspaces/caja-caliente-team-01/dashboard_state.json"
    )
