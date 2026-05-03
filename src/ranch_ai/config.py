from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


def _coerce_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """Parse a minimal subset of YAML for nested key/value configuration."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if not raw_value:
            nested: dict[str, Any] = {}
            parent[key] = nested
            stack.append((indent, nested))
        else:
            parent[key] = _coerce_scalar(raw_value)

    return root


def _load_yaml_or_simple_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        payload = yaml.safe_load(text) or {}
        return payload if isinstance(payload, dict) else {}
    return _simple_yaml_load(text)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(character in text for character in [":", "#", "{", "}", "[", "]", "\n"]) or text.strip() != text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _simple_yaml_dump(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, dict):
                lines.append(f"{prefix}{key}:")
                lines.extend(_simple_yaml_dump(child, indent + 2))
            elif isinstance(child, list):
                lines.append(f"{prefix}{key}:")
                for item in child:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.extend(_simple_yaml_dump(item, indent + 4))
                    else:
                        lines.append(f"{prefix}  - {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(child)}")
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def _merge_dataclass(instance: Any, overrides: dict[str, Any]) -> Any:
    for field_info in fields(instance):
        if field_info.name not in overrides:
            continue

        current_value = getattr(instance, field_info.name)
        override_value = overrides[field_info.name]

        if is_dataclass(current_value) and isinstance(override_value, dict):
            _merge_dataclass(current_value, override_value)
            continue

        if isinstance(current_value, Path):
            setattr(instance, field_info.name, Path(override_value))
            continue

        setattr(instance, field_info.name, override_value)

    return instance


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


@dataclass
class RanchConfig:
    name: str = "Caja Caliente"
    address: str = "711 N Scotty Road, Alpine, TX 79830"
    latitude: float = 29.606333
    longitude: float = -103.509750
    timezone: str = "America/Chicago"
    units: str = "imperial"


@dataclass
class WeatherConfig:
    provider: str = "mock"
    refresh_minutes: int = 30
    user_agent: str = "RangeIQ/0.1 (contact@example.com)"
    timeout_seconds: int = 10


@dataclass
class AlertsConfig:
    provider: str = "mock"
    refresh_minutes: int = 15
    timeout_seconds: int = 10


@dataclass
class SensorsConfig:
    provider: str = "csv"
    csv_path: str = "data/sensors/sensor_readings.csv"
    expected_interval_minutes: int = 60
    stale_after_minutes: int = 180
    offline_after_minutes: int = 720
    low_battery_voltage: float = 3.5
    low_signal_threshold: int = -110
    mock_days: int = 14


@dataclass
class SensorNetworkConfig:
    enabled: bool = True
    mode: str = "mock"
    expected_interval_minutes: int = 60
    stale_after_minutes: int = 180
    offline_after_minutes: int = 720
    sqlite_path: str = "data/processed/rangeiq_sensor_network.sqlite"
    station_registry_path: str = "data/sensors/station_registry.example.yaml"
    packet_limit: int = 240


@dataclass
class MeshtasticMQTTConfig:
    enabled: bool = False
    host: str = "localhost"
    port: int = 1883
    root_topic: str = "msh/US/2/json"
    channel_topic: str = "RangeIQ-Telemetry"
    username: str = ""
    password: str = ""


@dataclass
class MeshtasticSerialConfig:
    enabled: bool = False
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200


@dataclass
class MeshtasticConfig:
    region: str = "US"
    frequency_band: str = "915MHz"
    channel_name: str = "RangeIQ-Telemetry"
    use_private_channel: bool = True
    mqtt: MeshtasticMQTTConfig = field(default_factory=MeshtasticMQTTConfig)
    serial: MeshtasticSerialConfig = field(default_factory=MeshtasticSerialConfig)


@dataclass
class ThresholdsConfig:
    low_battery_voltage: float = 3.5
    low_signal_rssi: int = -115
    low_soil_moisture_pct: float = 15
    low_water_tank_pct: float = 25


@dataclass
class FireRiskConfig:
    high_wind_mph: float = 20
    high_gust_mph: float = 30
    low_humidity_pct: float = 25
    high_temperature_f: float = 90
    low_rainfall_7d_in: float = 0.10
    low_soil_moisture_pct: float = 15


@dataclass
class HistoricalWeatherSourceConfig:
    provider: str = "mock"
    timeout_seconds: int = 20
    refresh_hours: int = 168


@dataclass
class SoilsSourceConfig:
    provider: str = "mock"
    timeout_seconds: int = 20
    refresh_hours: int = 720


@dataclass
class DroughtSourceConfig:
    provider: str = "mock"
    timeout_seconds: int = 20
    refresh_hours: int = 48


@dataclass
class VegetationSourceConfig:
    provider: str = os.getenv("NDVI_PROVIDER", "earth_search_stac")
    timeout_seconds: int = 30
    refresh_hours: int = 336
    ndvi_refresh_hours: int = 168
    rap_refresh_hours: int = 720
    cache_ttl_days: int = int(os.getenv("VEGETATION_CACHE_TTL_DAYS", "30"))
    earth_search_stac_url: str = os.getenv("EARTH_SEARCH_STAC_URL", "https://earth-search.aws.element84.com/v1")
    ndvi_default_collection: str = os.getenv("NDVI_DEFAULT_COLLECTION", "sentinel-2-l2a")
    ndvi_cloud_cover_max: float = float(os.getenv("NDVI_CLOUD_COVER_MAX", "30"))
    ndvi_temporal_aggregation: str = "monthly_median"
    earth_search_max_items: int = 240
    climate_engine_api_key_env: str = "CLIMATE_ENGINE_API_KEY"
    appeears_username_env: str = "APPEEARS_USERNAME"
    appeears_password_env: str = "APPEEARS_PASSWORD"
    climate_engine_base_url: str = "https://geodata.dri.edu"
    climate_engine_dataset: str = "SENTINEL2"
    climate_engine_variable: str = "NDVI"
    climate_engine_area_reducer: str = "mean"
    rap_cover_url: str = "https://us-central1-rap-data-365417.cloudfunctions.net/coverV3"
    rap_cover_meteorology_url: str = "https://us-central1-rap-data-365417.cloudfunctions.net/coverMeteorologyV3"
    rap_production_url: str = "https://us-central1-rap-data-365417.cloudfunctions.net/productionV3"
    rap_production_16day_url: str = "https://us-central1-rap-data-365417.cloudfunctions.net/production16dayV3"
    max_aoi_acres: float = 500000.0
    notes: str = (
        "RangeIQ combines short-term NDVI greenness with long-term RAP cover and production history. "
        "Earth Search STAC is the default live NDVI source, while RAP remains the long-term range-health source."
    )


@dataclass
class PublicDataConfig:
    enabled: bool = True
    cache_enabled: bool = True
    historical_weather: HistoricalWeatherSourceConfig = field(default_factory=HistoricalWeatherSourceConfig)
    soils: SoilsSourceConfig = field(default_factory=SoilsSourceConfig)
    drought: DroughtSourceConfig = field(default_factory=DroughtSourceConfig)
    vegetation: VegetationSourceConfig = field(default_factory=VegetationSourceConfig)


@dataclass
class TrainingConfig:
    use_public_data: bool = True
    use_sensor_data: bool = True
    minimum_training_weeks: int = 12


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_data_dir: Path = PROJECT_ROOT / "data" / "processed"
    example_data_dir: Path = PROJECT_ROOT / "data" / "example"
    sensor_data_dir: Path = PROJECT_ROOT / "data" / "sensors"
    telemetry_data_dir: Path = PROJECT_ROOT / "data" / "telemetry"
    network_data_dir: Path = PROJECT_ROOT / "data" / "network"
    public_data_cache_dir: Path = PROJECT_ROOT / "data" / "cache" / "public_data"
    data_sources_cache_dir: Path = PROJECT_ROOT / "data" / "cache" / "data_sources"
    vegetation_cache_dir: Path = PROJECT_ROOT / "data" / "cache" / "vegetation"
    user_data_dir: Path = PROJECT_ROOT / "data" / "user"
    config_dir: Path = PROJECT_ROOT / "config"
    api_source_config_path: Path = PROJECT_ROOT / "config" / "api_sources.yaml"
    dashboard_state_path: Path = PROJECT_ROOT / "config" / "dashboard_state.json"
    default_pasture_path: Path = PROJECT_ROOT / "data" / "example" / "caja_caliente_ranch.geojson"
    default_sensor_output_path: Path = PROJECT_ROOT / "data" / "sensors" / "sensor_readings.csv"
    default_sensor_network_db_path: Path = PROJECT_ROOT / "data" / "processed" / "rangeiq_sensor_network.sqlite"
    default_station_registry_path: Path = PROJECT_ROOT / "data" / "sensors" / "station_registry.example.yaml"
    default_weekly_output_path: Path = PROJECT_ROOT / "data" / "processed" / "pasture_week_data.csv"
    default_scored_output_path: Path = PROJECT_ROOT / "data" / "processed" / "pasture_week_scored.csv"
    default_history_output_path: Path = PROJECT_ROOT / "data" / "processed" / "rangeiq_vegetation_history.csv"
    default_monthly_report_csv_path: Path = PROJECT_ROOT / "data" / "processed" / "rangeiq_monthly_report.csv"
    default_monthly_report_md_path: Path = PROJECT_ROOT / "data" / "processed" / "rangeiq_monthly_report.md"
    config_path: Path = PROJECT_ROOT / "config.yaml"
    config_example_path: Path = PROJECT_ROOT / "config.example.yaml"
    rangeiq_config_example_path: Path = PROJECT_ROOT / "config" / "rangeiq.example.yaml"
    meshtastic_config_example_path: Path = PROJECT_ROOT / "config" / "meshtastic.example.yaml"
    random_seed: int = 42
    default_weeks: int = 26
    default_history_years: int = 10
    default_hourly_sensor_days: int = 14
    boundary_status: str = "user-provided"
    app_name: str = "RangeIQ"
    pilot_name: str = "RangeIQ - Ranch Intelligence Pilot"
    ranch: RanchConfig = field(default_factory=RanchConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    sensors: SensorsConfig = field(default_factory=SensorsConfig)
    sensor_network: SensorNetworkConfig = field(default_factory=SensorNetworkConfig)
    meshtastic: MeshtasticConfig = field(default_factory=MeshtasticConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    fire_risk: FireRiskConfig = field(default_factory=FireRiskConfig)
    public_data: PublicDataConfig = field(default_factory=PublicDataConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)

    @property
    def default_ranch_name(self) -> str:
        return self.ranch.name

    @property
    def default_ranch_address(self) -> str:
        return self.ranch.address

    @property
    def center_lat(self) -> float:
        return self.ranch.latitude

    @property
    def center_lon(self) -> float:
        return self.ranch.longitude

    def to_display_dict(self) -> dict[str, Any]:
        return _serialize(self)


def load_settings(config_path: str | Path | None = None) -> Settings:
    loaded = Settings()
    path = Path(config_path) if config_path else loaded.config_path
    if path.exists():
        overrides = _load_yaml_or_simple_yaml(path)
        if isinstance(overrides, dict):
            _merge_dataclass(loaded, overrides)

    sensor_path = Path(loaded.sensors.csv_path)
    if not sensor_path.is_absolute():
        loaded.sensors.csv_path = str(loaded.project_root / sensor_path)
    network_db_path = Path(loaded.sensor_network.sqlite_path)
    if not network_db_path.is_absolute():
        loaded.sensor_network.sqlite_path = str(loaded.project_root / network_db_path)
    registry_path = Path(loaded.sensor_network.station_registry_path)
    if not registry_path.is_absolute():
        loaded.sensor_network.station_registry_path = str(loaded.project_root / registry_path)
    return loaded


def _relative_to_project_or_string(path_value: str | Path, project_root: Path) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return str(path)


def settings_to_config_payload(app_settings: Settings) -> dict[str, Any]:
    payload = {
        "ranch": _serialize(app_settings.ranch),
        "weather": _serialize(app_settings.weather),
        "alerts": _serialize(app_settings.alerts),
        "sensors": _serialize(app_settings.sensors),
        "sensor_network": _serialize(app_settings.sensor_network),
        "meshtastic": _serialize(app_settings.meshtastic),
        "thresholds": _serialize(app_settings.thresholds),
        "fire_risk": _serialize(app_settings.fire_risk),
        "public_data": _serialize(app_settings.public_data),
        "training": _serialize(app_settings.training),
    }
    payload["sensors"]["csv_path"] = _relative_to_project_or_string(app_settings.sensors.csv_path, app_settings.project_root)
    payload["sensor_network"]["sqlite_path"] = _relative_to_project_or_string(app_settings.sensor_network.sqlite_path, app_settings.project_root)
    payload["sensor_network"]["station_registry_path"] = _relative_to_project_or_string(
        app_settings.sensor_network.station_registry_path,
        app_settings.project_root,
    )
    return payload


def save_settings_file(app_settings: Settings, path: str | Path | None = None) -> Path:
    destination = Path(path) if path is not None else app_settings.config_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = settings_to_config_payload(app_settings)

    if yaml is not None:
        destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:  # pragma: no cover - fallback path only used without PyYAML
        destination.write_text("\n".join(_simple_yaml_dump(payload)) + "\n", encoding="utf-8")
    return destination


settings = load_settings()
