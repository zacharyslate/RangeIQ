import copy

from ranch_ai.config import load_settings, save_settings_file, settings, settings_to_config_payload


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
