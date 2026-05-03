from __future__ import annotations

import copy
import html
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
ICON_PATH = PROJECT_ROOT / "RangeIQ_icon_transparent.png"
FALLBACK_ICON_PATH = PROJECT_ROOT / "RangeIQ_icon.ico"
LIGHT_LOGO_PATH = PROJECT_ROOT / "RangeIQ_logo_transparent_light.png"
DARK_LOGO_PATH = PROJECT_ROOT / "RangeIQ_logo_transparent_dark.png"
FALLBACK_LOGO_PATH = PROJECT_ROOT / "RangeIQ_logo_white.png"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ranch_ai.config import Settings, normalize_workspace_id, save_settings_file, settings
from ranch_ai.pipeline import MvpArtifacts, run_mvp_pipeline
from ranch_ai.services import AlertService, AuthError, AuthService, AuthUser, WeatherService, assess_fire_risk
from ranch_ai.visualization.plots import (
    plot_condition_scores,
    plot_forage_trend,
    plot_long_term_vegetation_history,
    plot_ndvi_trend,
    plot_public_ndvi_history,
    plot_rainfall_deficit_history,
    plot_rainfall_trend,
    plot_recommendation_mix,
    plot_rap_cover_history,
    plot_rap_production_history,
    plot_water_vs_stocking_risk,
)


LIGHT_THEME = {
    "name": "High Plains Day",
    "color_scheme": "light",
    "background": "#f4ecdf",
    "background_alt": "#efe2cd",
    "app_background": """
        radial-gradient(circle at 10% 10%, rgba(255,255,255,0.22), transparent 22%),
        radial-gradient(circle at 90% 12%, rgba(191,143,71,0.08), transparent 18%),
        linear-gradient(180deg, var(--rq-bg) 0%, var(--rq-bg-alt) 100%)
    """,
    "card": "#fbf6ed",
    "card_alt": "#f3e7d4",
    "text": "#241a13",
    "muted": "#725c48",
    "border": "#d6c1a8",
    "grid": "#dac8b5",
    "accent": "#234f34",
    "accent_2": "#9c9a4e",
    "accent_3": "#bf8f47",
    "accent_4": "#9b5a39",
    "accent_5": "#2f6690",
    "header_ring": "#2c5b3a",
    "success": "#4c7f3a",
    "warning": "#b4742f",
    "danger": "#8a4730",
    "info_bg": "rgba(35,79,52,0.08)",
    "shadow": "rgba(66, 46, 27, 0.12)",
    "recommendation_colors": {
        "GRAZE": "#4f7d43",
        "REST": "#8f8850",
        "SUPPLEMENT": "#bf8f47",
        "REDUCE STOCKING": "#b66b3d",
        "DESTOCK WARNING": "#8a4730",
    },
    "recommendation_rgba": {
        "GRAZE": [79, 125, 67, 185],
        "REST": [143, 136, 80, 185],
        "SUPPLEMENT": [191, 143, 71, 185],
        "REDUCE STOCKING": [182, 107, 61, 185],
        "DESTOCK WARNING": [138, 71, 48, 190],
    },
    "colorway": ["#234f34", "#9c9a4e", "#bf8f47", "#9b5a39", "#2f6690", "#6d8f5b"],
}

DARK_THEME = {
    "name": "Mesquite Night",
    "color_scheme": "dark",
    "background": "#091423",
    "background_alt": "#16263a",
    "app_background": """
        radial-gradient(circle at 6% 7%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 11% 19%, rgba(255,255,255,0.14) 0 1px, transparent 2px),
        radial-gradient(circle at 14% 16%, rgba(255,255,255,0.22) 0 1px, transparent 2px),
        radial-gradient(circle at 19% 8%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 23% 22%, rgba(255,255,255,0.12) 0 1px, transparent 2px),
        radial-gradient(circle at 28% 10%, rgba(255,255,255,0.14) 0 1px, transparent 2px),
        radial-gradient(circle at 34% 6%, rgba(255,255,255,0.12) 0 1px, transparent 2px),
        radial-gradient(circle at 37% 15%, rgba(255,255,255,0.18) 0 1px, transparent 2px),
        radial-gradient(circle at 42% 18%, rgba(255,255,255,0.18) 0 1px, transparent 2px),
        radial-gradient(circle at 49% 11%, rgba(255,255,255,0.12) 0 1px, transparent 2px),
        radial-gradient(circle at 54% 20%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 58% 8%, rgba(255,255,255,0.14) 0 1px, transparent 2px),
        radial-gradient(circle at 64% 17%, rgba(255,255,255,0.14) 0 1px, transparent 2px),
        radial-gradient(circle at 68% 6%, rgba(255,255,255,0.12) 0 1px, transparent 2px),
        radial-gradient(circle at 72% 14%, rgba(255,255,255,0.2) 0 1px, transparent 2px),
        radial-gradient(circle at 77% 21%, rgba(255,255,255,0.14) 0 1px, transparent 2px),
        radial-gradient(circle at 83% 8%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 88% 11%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 92% 18%, rgba(255,255,255,0.12) 0 1px, transparent 2px),
        radial-gradient(circle at 96% 6%, rgba(255,255,255,0.16) 0 1px, transparent 2px),
        radial-gradient(circle at 50% 108%, rgba(210,167,101,0.22), transparent 32%),
        radial-gradient(circle at 14% 88%, rgba(126,161,107,0.1), transparent 22%),
        linear-gradient(180deg, #07101b 0%, #0b1830 48%, #18263a 78%, #251d18 100%)
    """,
    "card": "#18202b",
    "card_alt": "#221f23",
    "text": "#f0e4d3",
    "muted": "#c0ab94",
    "border": "#3d4b5f",
    "grid": "#2a3950",
    "accent": "#7ea16b",
    "accent_2": "#a3a35f",
    "accent_3": "#d2a765",
    "accent_4": "#c07a52",
    "accent_5": "#74a0c3",
    "header_ring": "#7ea16b",
    "success": "#82a96e",
    "warning": "#d2a765",
    "danger": "#d38059",
    "info_bg": "rgba(126,161,107,0.14)",
    "shadow": "rgba(0, 0, 0, 0.28)",
    "recommendation_colors": {
        "GRAZE": "#82a96e",
        "REST": "#a3a35f",
        "SUPPLEMENT": "#d2a765",
        "REDUCE STOCKING": "#c07a52",
        "DESTOCK WARNING": "#d38059",
    },
    "recommendation_rgba": {
        "GRAZE": [130, 169, 110, 185],
        "REST": [163, 163, 95, 185],
        "SUPPLEMENT": [210, 167, 101, 185],
        "REDUCE STOCKING": [192, 122, 82, 185],
        "DESTOCK WARNING": [211, 128, 89, 190],
    },
    "colorway": ["#82a96e", "#d2a765", "#74a0c3", "#c07a52", "#a3a35f", "#dbc2a0"],
}

SENSOR_VARIABLES = {
    "Air Temperature": ("air_temp_f", "Air Temperature (F)"),
    "Humidity": ("humidity_pct", "Humidity (%)"),
    "Rainfall": ("rainfall_in", "Rainfall (in)"),
    "Soil Moisture 10 cm": ("soil_moisture_10cm", "Soil Moisture 10 cm (%)"),
    "Soil Moisture 30 cm": ("soil_moisture_30cm", "Soil Moisture 30 cm (%)"),
    "Soil Temperature": ("soil_temp_f", "Soil Temperature (F)"),
    "Battery Voltage": ("battery_voltage", "Battery Voltage (V)"),
    "Signal Strength": ("signal_strength", "Signal Strength (dBm)"),
    "Water Tank": ("water_tank_pct", "Water Tank (%)"),
    "Trough Level": ("trough_level_pct", "Trough Level (%)"),
}

MAP_BASEMAP_LABELS = {
    "naip": "USGS NAIP Aerial",
    "satellite": "Satellite",
    "road": "Road",
    "light": "Light",
    "dark": "Dark",
    "plain": "Plain",
}

BASE_SESSION_DEFAULTS = {
    "theme_mode": "High Plains Day",
    "weeks": settings.default_weeks,
    "history_years": settings.default_history_years,
    "seed": settings.random_seed,
    "ranch_name": settings.ranch.name,
    "ranch_address": settings.ranch.address,
    "ranch_lat": settings.ranch.latitude,
    "ranch_lon": settings.ranch.longitude,
    "ranch_timezone": settings.ranch.timezone,
    "ranch_units": settings.ranch.units,
    "map_basemap": "naip",
    "weather_provider": settings.weather.provider,
    "alerts_provider": settings.alerts.provider,
    "sensor_provider": settings.sensors.provider,
    "historical_weather_provider": settings.public_data.historical_weather.provider,
    "soils_provider": settings.public_data.soils.provider,
    "drought_provider": settings.public_data.drought.provider,
    "vegetation_provider": settings.public_data.vegetation.provider,
    "public_cache_enabled": settings.public_data.cache_enabled,
    "historical_weather_refresh_hours": settings.public_data.historical_weather.refresh_hours,
    "soils_refresh_hours": settings.public_data.soils.refresh_hours,
    "drought_refresh_hours": settings.public_data.drought.refresh_hours,
    "vegetation_refresh_hours": settings.public_data.vegetation.refresh_hours,
    "sensor_network_mode": settings.sensor_network.mode,
    "sensor_network_packet_limit": settings.sensor_network.packet_limit,
    "expected_interval_minutes": settings.sensors.expected_interval_minutes,
    "stale_after_minutes": settings.sensors.stale_after_minutes,
    "offline_after_minutes": settings.sensors.offline_after_minutes,
    "low_battery_voltage": settings.sensors.low_battery_voltage,
    "low_signal_threshold": settings.sensors.low_signal_threshold,
    "network_low_signal_rssi": settings.thresholds.low_signal_rssi,
    "network_low_water_tank_pct": settings.thresholds.low_water_tank_pct,
    "high_wind_mph": settings.fire_risk.high_wind_mph,
    "high_gust_mph": settings.fire_risk.high_gust_mph,
    "low_humidity_pct": settings.fire_risk.low_humidity_pct,
    "high_temperature_f": settings.fire_risk.high_temperature_f,
    "low_rainfall_7d_in": settings.fire_risk.low_rainfall_7d_in,
    "low_soil_moisture_pct": settings.fire_risk.low_soil_moisture_pct,
}

AUTH_SESSION_KEYS = {
    "auth_user_id",
    "auth_email",
    "auth_full_name",
    "auth_workspace_id",
}


def load_dashboard_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or settings.dashboard_state_path
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_dashboard_state(payload: dict[str, Any], path: Path | None = None) -> Path:
    state_path = path or settings.dashboard_state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return state_path


def load_saved_boundary_from_state(state: dict[str, Any]) -> tuple[str | None, bytes | None, str]:
    boundary_info = state.get("saved_boundary", {}) if isinstance(state, dict) else {}
    if not isinstance(boundary_info, dict):
        return None, None, "default"

    path_value = boundary_info.get("path")
    filename = boundary_info.get("filename")
    if not path_value or not filename:
        return None, None, "default"

    boundary_path = Path(path_value)
    if not boundary_path.exists():
        return None, None, "default"

    try:
        return str(filename), boundary_path.read_bytes(), "saved"
    except OSError:
        return None, None, "default"


def session_defaults_for_state(state: dict[str, Any], auth_user: AuthUser | None = None) -> dict[str, Any]:
    defaults = dict(BASE_SESSION_DEFAULTS)
    if auth_user is not None:
        defaults["ranch_name"] = auth_user.ranch_name
        defaults["ranch_address"] = auth_user.ranch_address
        if auth_user.ranch_latitude is not None:
            defaults["ranch_lat"] = auth_user.ranch_latitude
        if auth_user.ranch_longitude is not None:
            defaults["ranch_lon"] = auth_user.ranch_longitude
    for persisted_key, persisted_value in state.get("session_state", {}).items():
        if persisted_key in defaults:
            defaults[persisted_key] = persisted_value
    return defaults


def get_theme(mode: str) -> dict[str, object]:
    return DARK_THEME if mode == "Mesquite Night" else LIGHT_THEME


def get_logo_path(mode: str) -> Path:
    if mode == "Mesquite Night" and DARK_LOGO_PATH.exists():
        return DARK_LOGO_PATH
    if mode != "Mesquite Night" and LIGHT_LOGO_PATH.exists():
        return LIGHT_LOGO_PATH
    if LIGHT_LOGO_PATH.exists():
        return LIGHT_LOGO_PATH
    if DARK_LOGO_PATH.exists():
        return DARK_LOGO_PATH
    return FALLBACK_LOGO_PATH


def sign_in_user(user: AuthUser) -> None:
    st.session_state["auth_user_id"] = user.user_id
    st.session_state["auth_email"] = user.email
    st.session_state["auth_full_name"] = user.full_name
    st.session_state["auth_workspace_id"] = user.workspace_id


def sign_out_user() -> None:
    for key in AUTH_SESSION_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("_loaded_workspace_id", None)
    st.session_state.pop("workspace_id", None)
    st.query_params.clear()


def get_authenticated_user(auth_service: AuthService) -> AuthUser | None:
    user_id = str(st.session_state.get("auth_user_id", "") or "").strip()
    if not user_id:
        return None
    user = auth_service.get_user_by_id(user_id)
    if user is None:
        sign_out_user()
        return None
    sign_in_user(user)
    return user


def render_auth_gate(auth_service: AuthService) -> AuthUser:
    current_user = get_authenticated_user(auth_service)
    if current_user is not None:
        return current_user

    st.title("RangeIQ Access")
    st.caption(
        "Create an account to keep your ranch boundary, settings, and latest RangeIQ setup private to you. "
        "Each account gets its own saved ranch workspace."
    )
    if LIGHT_LOGO_PATH.exists() or DARK_LOGO_PATH.exists() or FALLBACK_LOGO_PATH.exists():
        st.image(str(LIGHT_LOGO_PATH if LIGHT_LOGO_PATH.exists() else FALLBACK_LOGO_PATH), width=280)

    login_tab, signup_tab = st.tabs(["Log In", "Create Account"])

    with login_tab:
        with st.form("rangeiq_login_form", clear_on_submit=False):
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submitted = st.form_submit_button("Log In")

        if login_submitted:
            try:
                user = auth_service.authenticate_user(email=login_email, password=login_password)
            except AuthError as exc:
                st.error(str(exc))
            else:
                sign_in_user(user)
                st.query_params["workspace"] = user.workspace_id
                st.rerun()

    with signup_tab:
        with st.form("rangeiq_signup_form", clear_on_submit=False):
            signup_name = st.text_input("Your Name", key="signup_name")
            signup_email = st.text_input("Email", key="signup_email")
            signup_password = st.text_input("Password", type="password", key="signup_password")
            signup_password_confirm = st.text_input("Confirm Password", type="password", key="signup_password_confirm")
            signup_ranch_name = st.text_input("Ranch Name", value=settings.ranch.name, key="signup_ranch_name")
            signup_ranch_address = st.text_input("Ranch Address", value=settings.ranch.address, key="signup_ranch_address")
            signup_lat = st.number_input("Latitude", value=float(settings.ranch.latitude), format="%.6f", key="signup_ranch_lat")
            signup_lon = st.number_input("Longitude", value=float(settings.ranch.longitude), format="%.6f", key="signup_ranch_lon")
            signup_submitted = st.form_submit_button("Create Account")

        if signup_submitted:
            if signup_password != signup_password_confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    user = auth_service.create_user(
                        email=signup_email,
                        password=signup_password,
                        full_name=signup_name,
                        ranch_name=signup_ranch_name,
                        ranch_address=signup_ranch_address,
                        ranch_latitude=float(signup_lat),
                        ranch_longitude=float(signup_lon),
                    )
                except AuthError as exc:
                    st.error(str(exc))
                else:
                    sign_in_user(user)
                    st.query_params["workspace"] = user.workspace_id
                    st.rerun()

    st.stop()


def resolve_workspace_id(auth_user: AuthUser | None = None) -> str:
    if auth_user is not None:
        normalized = normalize_workspace_id(auth_user.workspace_id, fallback=f"user-{auth_user.user_id[:8]}")
        if st.query_params.get("workspace") != normalized:
            st.query_params["workspace"] = normalized
        return normalized
    raw_value = st.query_params.get("workspace", "")
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else ""
    normalized = normalize_workspace_id(str(raw_value), fallback="")
    if normalized:
        if str(raw_value) != normalized:
            st.query_params["workspace"] = normalized
        return normalized

    generated = normalize_workspace_id(f"workspace-{uuid4().hex[:8]}")
    st.query_params["workspace"] = generated
    return generated


def initialize_session_state(workspace_id: str, session_defaults: dict[str, Any]) -> None:
    if st.session_state.get("_loaded_workspace_id") != workspace_id:
        for key, value in session_defaults.items():
            st.session_state[key] = value
        st.session_state["_loaded_workspace_id"] = workspace_id
    else:
        for key, value in session_defaults.items():
            st.session_state.setdefault(key, value)
    st.session_state["workspace_id"] = workspace_id


page_icon_path = ICON_PATH if ICON_PATH.exists() else FALLBACK_ICON_PATH
PAGE_ICON = Image.open(page_icon_path) if page_icon_path.exists() else None
st.set_page_config(page_title=f"{settings.app_name} | Operational Dashboard", page_icon=PAGE_ICON, layout="wide")
AUTH_SERVICE = AuthService(settings.auth_db_path)
CURRENT_USER = render_auth_gate(AUTH_SERVICE)
CURRENT_WORKSPACE_ID = resolve_workspace_id(CURRENT_USER)
WORKSPACE_STATE_PATH = settings.workspace_state_path_for(CURRENT_WORKSPACE_ID)
PERSISTED_DASHBOARD_STATE = load_dashboard_state(WORKSPACE_STATE_PATH)
SESSION_DEFAULTS = session_defaults_for_state(PERSISTED_DASHBOARD_STATE, CURRENT_USER)
initialize_session_state(CURRENT_WORKSPACE_ID, SESSION_DEFAULTS)


def load_artifacts(
    runtime_settings: Settings,
    geojson_text: str | None,
    uploaded_boundary_name: str | None,
    uploaded_boundary_bytes: bytes | None,
    weeks: int,
    history_years: int,
    seed: int,
) -> MvpArtifacts:
    return run_mvp_pipeline(
        geojson_text=geojson_text,
        uploaded_boundary_name=uploaded_boundary_name,
        uploaded_boundary_bytes=uploaded_boundary_bytes,
        weeks=weeks,
        history_years=history_years,
        seed=seed,
        write_outputs=False,
        app_settings=runtime_settings,
    )


def _hash_settings(app_settings: Settings) -> str:
    return json.dumps(app_settings.to_display_dict(), sort_keys=True, default=str)


def _refresh_bucket(minutes: int) -> str:
    safe_minutes = max(int(minutes), 1)
    return pd.Timestamp.now(tz="UTC").floor(f"{safe_minutes}min").isoformat()


load_artifacts = st.cache_data(
    show_spinner="Building the RangeIQ scenario...",
    hash_funcs={Settings: _hash_settings},
    max_entries=8,
)(load_artifacts)


@st.cache_data(show_spinner=False, hash_funcs={Settings: _hash_settings}, max_entries=12)
def load_weather_bundle_cached(
    runtime_settings: Settings,
    lat: float,
    lon: float,
    provider: str,
    refresh_bucket: str,
):
    del refresh_bucket
    weather_service = WeatherService(runtime_settings)
    return weather_service.load_weather_bundle(lat=lat, lon=lon, provider=provider)


@st.cache_data(show_spinner=False, hash_funcs={Settings: _hash_settings}, max_entries=12)
def load_alert_bundle_cached(
    runtime_settings: Settings,
    lat: float,
    lon: float,
    provider: str,
    refresh_bucket: str,
):
    del refresh_bucket
    alert_service = AlertService(runtime_settings)
    return alert_service.load_alert_bundle(lat=lat, lon=lon, provider=provider)


def apply_app_theme(theme: dict[str, object]) -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --rq-bg: {theme['background']};
            --rq-bg-alt: {theme['background_alt']};
            --rq-card: {theme['card']};
            --rq-card-alt: {theme['card_alt']};
            --rq-text: {theme['text']};
            --rq-muted: {theme['muted']};
            --rq-border: {theme['border']};
            --rq-grid: {theme['grid']};
            --rq-accent: {theme['accent']};
            --rq-accent-2: {theme['accent_2']};
            --rq-accent-3: {theme['accent_3']};
            --rq-accent-4: {theme['accent_4']};
            --rq-success: {theme['success']};
            --rq-warning: {theme['warning']};
            --rq-danger: {theme['danger']};
            --rq-shadow: {theme['shadow']};
            --rq-info: {theme['info_bg']};
        }}
        html, body {{
            color-scheme: {theme['color_scheme']};
        }}
        .stApp {{
            background: {theme['app_background']};
            color: var(--rq-text);
            color-scheme: {theme['color_scheme']};
        }}
        [data-testid="stAppViewContainer"],
        [data-testid="stSidebar"] {{
            color-scheme: {theme['color_scheme']};
        }}
        [data-testid="stAppViewContainer"] > .main .block-container {{
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1480px;
        }}
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu {{
            display: none !important;
        }}
        [data-testid="stVerticalBlock"] {{
            gap: 0.9rem;
        }}
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border-right: 1px solid var(--rq-border);
        }}
        [data-testid="stSidebar"] * {{
            color: var(--rq-text);
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{
            color: var(--rq-text);
        }}
        .stMarkdown p {{
            color: var(--rq-text);
        }}
        [data-testid="stMetric"] {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 10px 24px var(--rq-shadow);
        }}
        [data-testid="stMetricLabel"] {{
            color: var(--rq-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        [data-testid="stMetricValue"] {{
            color: var(--rq-accent);
        }}
        div[data-testid="stExpander"], div[data-testid="stDataFrame"], div.stPlotlyChart {{
            border-radius: 18px;
        }}
        div[data-testid="stExpander"], div[data-testid="stDataFrame"], div.stPlotlyChart {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            box-shadow: 0 10px 24px var(--rq-shadow);
            padding: 6px;
        }}
        [data-testid="stTabs"] {{
            margin-top: 0.1rem;
        }}
        [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            gap: 0.55rem;
            padding-bottom: 0.25rem;
        }}
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
            background: transparent !important;
            height: 0 !important;
        }}
        [data-testid="stTabs"] button {{
            min-height: 48px;
            padding: 0.55rem 1.05rem;
            border-radius: 999px;
            border: 1px solid var(--rq-border);
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            color: var(--rq-muted);
            box-shadow: 0 6px 16px rgba(66, 46, 27, 0.08);
            transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
        }}
        [data-testid="stTabs"] button:hover {{
            transform: translateY(-1px);
            border-color: var(--rq-accent-3);
            box-shadow: 0 10px 22px rgba(66, 46, 27, 0.12);
        }}
        [data-testid="stTabs"] button p {{
            margin: 0;
            color: var(--rq-muted);
            font-size: 0.95rem;
            font-weight: 600;
            line-height: 1;
            white-space: nowrap;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            background: linear-gradient(135deg, var(--rq-accent) 0%, var(--rq-accent-2) 100%);
            color: white;
            border-color: transparent;
            box-shadow: 0 12px 24px rgba(35, 79, 52, 0.24);
        }}
        [data-testid="stTabs"] button[aria-selected="true"] p {{
            color: white;
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stNumberInput div[data-baseweb="input"] > div,
        .stTextInput div[data-baseweb="input"] > div,
        .stMultiSelect div[data-baseweb="select"] > div,
        .stDateInput > div > div,
        .stTextArea textarea,
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input,
        .stTextArea textarea,
        .stMultiSelect input,
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span {{
            background: var(--rq-card) !important;
            border: 1px solid var(--rq-border) !important;
            color: var(--rq-text) !important;
            -webkit-text-fill-color: var(--rq-text) !important;
            box-shadow: none !important;
        }}
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        .stDateInput input::placeholder,
        .stTextArea textarea::placeholder,
        .stMultiSelect input::placeholder,
        div[data-baseweb="select"] input::placeholder {{
            color: var(--rq-muted) !important;
            -webkit-text-fill-color: var(--rq-muted) !important;
            opacity: 0.9 !important;
        }}
        div[data-baseweb="select"] svg,
        .stDateInput svg,
        .stMultiSelect svg,
        .stNumberInput svg,
        .stTextInput svg {{
            fill: var(--rq-muted) !important;
            color: var(--rq-muted) !important;
        }}
        div[data-baseweb="select"] *:focus,
        div[data-baseweb="input"] *:focus,
        .stTextArea textarea:focus,
        .stTextInput input:focus,
        .stNumberInput input:focus,
        .stDateInput input:focus,
        .stMultiSelect input:focus {{
            border-color: var(--rq-accent-3) !important;
            box-shadow: 0 0 0 1px var(--rq-accent-3) !important;
        }}
        .stButton > button,
        .stDownloadButton > button {{
            background: linear-gradient(90deg, var(--rq-accent) 0%, var(--rq-accent-2) 100%);
            color: white;
            border: none;
            border-radius: 999px;
            padding: 0.55rem 1rem;
        }}
        div[data-testid="stAlert"] {{
            background: var(--rq-info);
            border: 1px solid var(--rq-border);
            color: var(--rq-text);
            border-radius: 18px;
        }}
        .rq-card {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 20px;
            padding: 1rem 1.05rem;
            box-shadow: 0 10px 24px var(--rq-shadow);
        }}
        .rq-hero-card {{
            min-height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .rq-hero-kicker {{
            color: var(--rq-muted);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.76rem;
            margin-bottom: 0.45rem;
        }}
        .rq-hero-title {{
            color: var(--rq-accent);
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.05;
            margin-bottom: 0.45rem;
        }}
        .rq-hero-meta {{
            color: var(--rq-muted);
            font-size: 0.95rem;
            line-height: 1.55;
        }}
        .rq-card-title {{
            color: var(--rq-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.78rem;
            margin-bottom: 0.45rem;
        }}
        .rq-card-value {{
            color: var(--rq-accent);
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }}
        .rq-card-subtext {{
            color: var(--rq-muted);
            font-size: 0.92rem;
            line-height: 1.4;
        }}
        .rq-badge {{
            display: inline-block;
            padding: 0.18rem 0.65rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 600;
            margin-right: 0.35rem;
            border: 1px solid var(--rq-border);
        }}
        .rq-badge-critical {{
            background: rgba(138, 71, 48, 0.18);
            color: var(--rq-danger);
        }}
        .rq-badge-warning {{
            background: rgba(180, 116, 47, 0.16);
            color: var(--rq-warning);
        }}
        .rq-badge-success {{
            background: rgba(76, 127, 58, 0.16);
            color: var(--rq-success);
        }}
        .rq-badge-info {{
            background: rgba(47, 102, 144, 0.16);
            color: var(--rq-accent-5);
        }}
        .rq-list {{
            margin: 0.4rem 0 0 1rem;
            color: var(--rq-text);
        }}
        .rq-list li {{
            margin-bottom: 0.3rem;
        }}
        .rq-inline-note {{
            color: var(--rq-muted);
            font-size: 0.9rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_chart_theme(figure, theme: dict[str, object]):
    figure.update_layout(
        paper_bgcolor=theme["card"],
        plot_bgcolor=theme["card"],
        font=dict(color=theme["text"]),
        title_font=dict(color=theme["text"], size=20),
        colorway=theme["colorway"],
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=theme["muted"])),
        margin=dict(l=18, r=18, t=42, b=14),
    )
    if figure.layout.height is None:
        figure.update_layout(height=325)
    figure.update_xaxes(
        gridcolor=theme["grid"],
        linecolor=theme["border"],
        tickfont=dict(color=theme["muted"]),
        title_font=dict(color=theme["muted"]),
        zeroline=False,
    )
    figure.update_yaxes(
        gridcolor=theme["grid"],
        linecolor=theme["border"],
        tickfont=dict(color=theme["muted"]),
        title_font=dict(color=theme["muted"]),
        zeroline=False,
    )
    return figure


def format_number(value: Any, suffix: str = "", decimals: int = 0, default: str = "--") -> str:
    if value is None or pd.isna(value):
        return default
    return f"{float(value):,.{decimals}f}{suffix}"


def format_timestamp(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M")


def filter_time_range_by_column(df: pd.DataFrame, column: str, time_range: str) -> pd.DataFrame:
    filtered = df.copy()
    if filtered.empty or time_range not in {"24h", "7d", "30d"}:
        return filtered
    cutoff = pd.to_datetime(filtered[column]).max() - pd.Timedelta(hours={"24h": 24, "7d": 24 * 7, "30d": 24 * 30}[time_range])
    return filtered.loc[pd.to_datetime(filtered[column]) >= cutoff].copy()


def status_badge(mode: str) -> str:
    tone = "success"
    label = mode.upper()
    if "fallback" in mode:
        tone = "warning"
    elif mode in {"mock", "csv"}:
        tone = "info"
    return f"<span class='rq-badge rq-badge-{tone}'>{html.escape(label)}</span>"


def highlight_badge(level: str, label: str) -> str:
    mapped = "info"
    if level == "critical":
        mapped = "critical"
    elif level == "warning":
        mapped = "warning"
    elif level == "success":
        mapped = "success"
    return f"<span class='rq-badge rq-badge-{mapped}'>{html.escape(label)}</span>"


def friendly_trend_label(value: str | None) -> str:
    mapping = {
        "increasing": "Improving",
        "stable": "Stable",
        "declining": "Declining",
        "unknown": "Unknown",
    }
    return mapping.get(str(value or "unknown").lower(), str(value or "Unknown"))


def friendly_ndvi_status(value: str | None) -> str:
    mapping = {
        "Above normal": "Greener than normal",
        "Normal": "Near normal",
        "Below normal": "Below normal growth",
        "Unknown": "Unknown",
    }
    return mapping.get(str(value or "Normal"), str(value or "Normal"))


def render_signal_card(title: str, value: str, subtitle: str, badges: list[str] | None = None) -> None:
    badges_html = "".join(badges or [])
    st.markdown(
        (
            "<div class='rq-card'>"
            f"<div class='rq-card-title'>{html.escape(title)}</div>"
            f"<div class='rq-card-value'>{html.escape(value)}</div>"
            f"<div class='rq-card-subtext'>{html.escape(subtitle)}</div>"
            f"<div style='margin-top:0.65rem'>{badges_html}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_dashboard_header(
    runtime_settings: Settings,
    last_updated: pd.Timestamp,
    total_acres: float,
    pasture_count: int,
    boundary_mode: str,
    map_basemap: str,
) -> None:
    pasture_label = "1 pasture" if pasture_count == 1 else f"{pasture_count} pastures"
    boundary_badge = highlight_badge("info", "DEFAULT BOUNDARY")
    if boundary_mode == "uploaded":
        boundary_badge = highlight_badge("success", "UPLOADED BOUNDARY")
    elif boundary_mode == "saved":
        boundary_badge = highlight_badge("success", "SAVED BOUNDARY")
    basemap_badge = highlight_badge("info", f"{MAP_BASEMAP_LABELS.get(map_basemap, map_basemap).upper()} MAP")
    st.markdown(
        (
            "<div class='rq-card rq-hero-card'>"
            f"<div class='rq-hero-kicker'>{html.escape(runtime_settings.pilot_name)}</div>"
            f"<div class='rq-hero-title'>{html.escape(runtime_settings.ranch.name)}</div>"
            f"<div class='rq-hero-meta'>{html.escape(runtime_settings.ranch.address)}</div>"
            f"<div class='rq-hero-meta'>{runtime_settings.ranch.latitude:.4f}, {runtime_settings.ranch.longitude:.4f} | "
            f"{pasture_label} | {total_acres:,.1f} acres | Updated {last_updated.strftime('%Y-%m-%d %H:%M')}</div>"
            f"<div style='margin-top:0.8rem'>{boundary_badge}{basemap_badge}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def build_runtime_settings() -> Settings:
    runtime = copy.deepcopy(settings)
    runtime.ranch.name = st.session_state.ranch_name
    runtime.ranch.address = st.session_state.ranch_address
    runtime.ranch.latitude = float(st.session_state.ranch_lat)
    runtime.ranch.longitude = float(st.session_state.ranch_lon)
    runtime.ranch.timezone = st.session_state.ranch_timezone
    runtime.ranch.units = st.session_state.ranch_units
    runtime.weather.provider = st.session_state.weather_provider
    runtime.alerts.provider = st.session_state.alerts_provider
    runtime.sensors.provider = st.session_state.sensor_provider
    runtime.public_data.cache_enabled = bool(st.session_state.public_cache_enabled)
    runtime.public_data.historical_weather.provider = st.session_state.historical_weather_provider
    runtime.public_data.historical_weather.refresh_hours = int(st.session_state.historical_weather_refresh_hours)
    runtime.public_data.soils.provider = st.session_state.soils_provider
    runtime.public_data.soils.refresh_hours = int(st.session_state.soils_refresh_hours)
    runtime.public_data.drought.provider = st.session_state.drought_provider
    runtime.public_data.drought.refresh_hours = int(st.session_state.drought_refresh_hours)
    runtime.public_data.vegetation.provider = st.session_state.vegetation_provider
    runtime.public_data.vegetation.refresh_hours = int(st.session_state.vegetation_refresh_hours)
    runtime.sensor_network.mode = st.session_state.sensor_network_mode
    runtime.sensor_network.packet_limit = int(st.session_state.sensor_network_packet_limit)
    runtime.sensors.expected_interval_minutes = int(st.session_state.expected_interval_minutes)
    runtime.sensors.stale_after_minutes = int(st.session_state.stale_after_minutes)
    runtime.sensors.offline_after_minutes = int(st.session_state.offline_after_minutes)
    runtime.sensors.low_battery_voltage = float(st.session_state.low_battery_voltage)
    runtime.sensors.low_signal_threshold = int(st.session_state.low_signal_threshold)
    runtime.thresholds.low_battery_voltage = float(st.session_state.low_battery_voltage)
    runtime.thresholds.low_signal_rssi = int(st.session_state.network_low_signal_rssi)
    runtime.thresholds.low_water_tank_pct = float(st.session_state.network_low_water_tank_pct)
    runtime.fire_risk.high_wind_mph = float(st.session_state.high_wind_mph)
    runtime.fire_risk.high_gust_mph = float(st.session_state.high_gust_mph)
    runtime.fire_risk.low_humidity_pct = float(st.session_state.low_humidity_pct)
    runtime.fire_risk.high_temperature_f = float(st.session_state.high_temperature_f)
    runtime.fire_risk.low_rainfall_7d_in = float(st.session_state.low_rainfall_7d_in)
    runtime.fire_risk.low_soil_moisture_pct = float(st.session_state.low_soil_moisture_pct)
    runtime.training.use_sensor_data = False
    return runtime


def persist_boundary_file(filename: str, payload: bytes, workspace_id: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".geojson"
    destination_dir = settings.workspace_boundary_dir_for(workspace_id)
    destination = destination_dir / f"saved_boundary{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    for existing in destination.parent.glob("saved_boundary.*"):
        if existing != destination and existing.is_file():
            existing.unlink(missing_ok=True)
    destination.write_bytes(payload)
    return destination


def build_dashboard_state_payload(
    runtime_settings: Settings,
    *,
    workspace_id: str,
    boundary_filename: str | None,
    boundary_bytes: bytes | None,
    existing_state: dict[str, Any],
) -> dict[str, Any]:
    normalized_workspace_id = normalize_workspace_id(workspace_id, fallback=CURRENT_WORKSPACE_ID)
    config_path = save_settings_file(runtime_settings, path=runtime_settings.workspace_config_path_for(normalized_workspace_id))
    session_payload = {key: st.session_state.get(key) for key in BASE_SESSION_DEFAULTS}
    boundary_payload: dict[str, Any] = {}

    if boundary_filename is not None and boundary_bytes is not None:
        saved_boundary_path = persist_boundary_file(boundary_filename, boundary_bytes, normalized_workspace_id)
        boundary_payload = {
            "filename": boundary_filename,
            "path": str(saved_boundary_path),
        }
    elif isinstance(existing_state.get("saved_boundary"), dict):
        existing_boundary_path = existing_state["saved_boundary"].get("path")
        if existing_boundary_path and Path(existing_boundary_path).exists():
            boundary_payload = dict(existing_state["saved_boundary"])

    return {
        "workspace_id": normalized_workspace_id,
        "saved_at": pd.Timestamp.now().isoformat(),
        "config_path": str(config_path),
        "session_state": session_payload,
        "saved_boundary": boundary_payload,
    }


def render_under_development_notice(title: str, detail: str) -> None:
    st.subheader(title)
    st.info(
        f"{title} is currently under development and temporarily disabled in the hosted app. {detail}"
    )


def _rgba_to_css(color: list[int] | tuple[int, ...], opacity_override: float | None = None) -> str:
    rgba = list(color)
    alpha = opacity_override if opacity_override is not None else ((rgba[3] / 255.0) if len(rgba) > 3 else 1.0)
    return f"rgba({int(rgba[0])}, {int(rgba[1])}, {int(rgba[2])}, {alpha:.3f})"


def _polygon_bounds(latest_snapshot: pd.DataFrame) -> tuple[float, float, float, float]:
    all_lons: list[float] = []
    all_lats: list[float] = []
    for polygon in latest_snapshot["geometry"]:
        for lon, lat in polygon:
            all_lons.append(float(lon))
            all_lats.append(float(lat))

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)
    lon_pad = max((max_lon - min_lon) * 0.18, 0.00035)
    lat_pad = max((max_lat - min_lat) * 0.18, 0.00035)
    return min_lon - lon_pad, min_lat - lat_pad, max_lon + lon_pad, max_lat + lat_pad


def build_naip_map_html(latest_snapshot: pd.DataFrame, theme: dict[str, object]) -> str:
    recommendation_rgba = theme["recommendation_rgba"]
    polygon_records = []

    for row in latest_snapshot.itertuples(index=False):
        polygon_records.append(
            {
                "name": row.name,
                "pasture_id": row.pasture_id,
                "path": [[float(point[1]), float(point[0])] for point in row.geometry],
                "recommendation": row.recommendation,
                "condition_score": float(row.pasture_condition_score),
                "grazing_pressure": float(row.grazing_pressure),
                "water_risk_score": float(row.water_risk_score),
                "stocking_risk_score": float(row.stocking_risk_score),
                "fill_color": _rgba_to_css(recommendation_rgba[row.recommendation], opacity_override=0.22),
                "line_color": _rgba_to_css(recommendation_rgba[row.recommendation], opacity_override=0.95),
            }
        )

    min_lon, min_lat, max_lon, max_lat = _polygon_bounds(latest_snapshot)
    map_bounds = [[min_lat, min_lon], [max_lat, max_lon]]
    polygon_json = json.dumps(polygon_records)
    bounds_json = json.dumps(map_bounds)
    border_color = str(theme["border"])
    card_color = str(theme["card"])

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background: {card_color};
        }}
        #naip-map {{
          width: 100%;
          height: 440px;
          border-radius: 20px;
          overflow: hidden;
          border: 1px solid {border_color};
          background: {card_color};
        }}
        .leaflet-container {{
          font-family: Georgia, "Times New Roman", serif;
          background: {card_color};
        }}
      </style>
    </head>
    <body>
      <div id="naip-map"></div>
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        const polygons = {polygon_json};
        const bounds = {bounds_json};
        const map = L.map('naip-map', {{
          zoomControl: true,
          attributionControl: true,
          scrollWheelZoom: false
        }});

        L.tileLayer(
          'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{{z}}/{{y}}/{{x}}',
          {{
            attribution: 'USGS The National Map Imagery',
            maxZoom: 20,
            maxNativeZoom: 16
          }}
        ).addTo(map);

        polygons.forEach((polygon) => {{
          const popup = `
            <div style="min-width:190px">
              <div style="font-weight:700; margin-bottom:0.35rem">${{polygon.name}}</div>
              <div>Recommendation: ${{polygon.recommendation}}</div>
              <div>Condition score: ${{polygon.condition_score.toFixed(1)}}</div>
              <div>Grazing pressure: ${{polygon.grazing_pressure.toFixed(2)}}</div>
              <div>Water risk: ${{polygon.water_risk_score.toFixed(1)}}</div>
              <div>Stocking risk: ${{polygon.stocking_risk_score.toFixed(1)}}</div>
            </div>
          `;

          L.polygon(polygon.path, {{
            color: polygon.line_color,
            weight: 3,
            fillColor: polygon.fill_color,
            fillOpacity: 1.0
          }}).addTo(map).bindPopup(popup);
        }});

        map.fitBounds(bounds, {{ padding: [18, 18] }});
      </script>
    </body>
    </html>
    """


def build_map_layer(latest_snapshot: pd.DataFrame, theme: dict[str, object], basemap: str) -> pdk.Deck:
    records = []
    recommendation_rgba = theme["recommendation_rgba"]
    total_acres = float(latest_snapshot["acres"].sum()) if "acres" in latest_snapshot.columns else 0.0
    for row in latest_snapshot.itertuples(index=False):
        records.append(
            {
                "name": row.name,
                "pasture_id": row.pasture_id,
                "polygon": row.geometry,
                "recommendation": row.recommendation,
                "condition_score": row.pasture_condition_score,
                "grazing_pressure": row.grazing_pressure,
                "water_risk_score": row.water_risk_score,
                "stocking_risk_score": row.stocking_risk_score,
                "fill_color": recommendation_rgba[row.recommendation],
            }
        )

    zoom = 11
    if len(latest_snapshot) == 1 or total_acres <= 20:
        zoom = 16
    elif total_acres <= 200:
        zoom = 13

    view_state = pdk.ViewState(
        latitude=float(latest_snapshot["centroid_lat"].mean()),
        longitude=float(latest_snapshot["centroid_lon"].mean()),
        zoom=zoom,
        pitch=22,
    )
    layer = pdk.Layer(
        "PolygonLayer",
        data=records,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color=[32, 24, 18],
        line_width_min_pixels=1.5,
        pickable=True,
        stroked=True,
        filled=True,
    )
    tooltip = {
        "html": (
            "<b>{name}</b><br/>"
            "Recommendation: {recommendation}<br/>"
            "Condition score: {condition_score}<br/>"
            "Grazing pressure: {grazing_pressure}<br/>"
            "Water risk: {water_risk_score}<br/>"
            "Stocking risk: {stocking_risk_score}"
        ),
        "style": {"backgroundColor": theme["card"], "color": theme["text"], "border": f"1px solid {theme['border']}"},
    }
    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_provider=None if basemap == "plain" else "carto",
        map_style=None if basemap == "plain" else basemap,
    )


def render_pasture_map(latest_snapshot: pd.DataFrame, theme: dict[str, object], basemap: str) -> None:
    if basemap == "naip":
        try:
            components.html(build_naip_map_html(latest_snapshot, theme), height=456)
            return
        except Exception as exc:
            st.warning(f"USGS NAIP imagery was unavailable, so RangeIQ switched back to the standard map. {exc}")

    st.pydeck_chart(build_map_layer(latest_snapshot, theme, basemap), width="stretch")


def plot_fire_risk_gauge(score: float, category: str, color: str, theme: dict[str, object]):
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "", "font": {"size": 42, "color": theme["text"]}},
            title={"text": f"Fire Risk: {category}", "font": {"size": 18, "color": theme["text"]}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": theme["muted"]},
                "bar": {"color": color},
                "bgcolor": theme["card_alt"],
                "steps": [
                    {"range": [0, 25], "color": "rgba(76,127,58,0.18)"},
                    {"range": [25, 45], "color": "rgba(180,116,47,0.18)"},
                    {"range": [45, 65], "color": "rgba(191,143,71,0.18)"},
                    {"range": [65, 85], "color": "rgba(169,83,52,0.18)"},
                    {"range": [85, 100], "color": "rgba(135,55,37,0.24)"},
                ],
                "threshold": {"line": {"color": theme["danger"], "width": 3}, "thickness": 0.8, "value": score},
            },
        )
    )
    figure.update_layout(height=280, margin=dict(l=18, r=18, t=56, b=12))
    return apply_chart_theme(figure, theme)


def prepare_forecast_table(forecast_df: pd.DataFrame) -> pd.DataFrame:
    display_df = forecast_df.copy()
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(display_df["date"]).astype(str)
    rename_map = {
        "date": "Date",
        "weather_label": "Forecast",
        "high_temp_f": "High (F)",
        "low_temp_f": "Low (F)",
        "precip_probability_pct": "Precip Chance (%)",
        "expected_precip_in": "Precip (in)",
        "wind_speed_mph": "Wind (mph)",
        "wind_gust_mph": "Gust (mph)",
        "wind_direction": "Wind Dir",
    }
    display_df = display_df.rename(columns=rename_map)
    ordered_columns = [column for column in rename_map.values() if column in display_df.columns]
    for column in ["High (F)", "Low (F)", "Precip Chance (%)", "Precip (in)", "Wind (mph)", "Gust (mph)"]:
        if column in display_df.columns:
            display_df[column] = pd.to_numeric(display_df[column], errors="coerce").round(1)
    return display_df[ordered_columns]


def render_alert_panel(alerts_df: pd.DataFrame) -> None:
    st.subheader("Active Warnings")
    if alerts_df.empty:
        st.success("No active warnings for this ranch location.")
        return

    for row in alerts_df.itertuples(index=False):
        badges = "".join(
            [
                highlight_badge(row.highlight_level, row.event),
                highlight_badge("warning" if row.relevance == "HIGH" else "info", f"Relevance: {row.relevance}"),
                highlight_badge("info", f"Severity: {row.severity}"),
            ]
        )
        st.markdown(
            (
                "<div class='rq-card' style='margin-bottom:0.7rem'>"
                f"<div style='margin-bottom:0.45rem'>{badges}</div>"
                f"<div style='font-weight:700; font-size:1.15rem'>{html.escape(str(row.headline))}</div>"
                f"<div class='rq-inline-note'>Effective: {format_timestamp(row.effective)} | Expires: {format_timestamp(row.expires)}</div>"
                f"<p style='margin:0.6rem 0 0.35rem 0'>{html.escape(str(row.description))}</p>"
                f"<div class='rq-inline-note'>Source: {html.escape(str(row.source))}</div>"
                f"<div class='rq-card-subtext' style='margin-top:0.5rem'><b>Operational concern:</b> {html.escape(str(row.operational_concern))}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_fire_risk_panel(assessment) -> None:
    st.subheader("Fire & Drought Risk")
    driver_html = "".join(f"<li>{html.escape(driver)}</li>" for driver in assessment.main_drivers)
    action_html = "".join(f"<li>{html.escape(action)}</li>" for action in assessment.recommended_actions)
    st.markdown(
        (
            "<div class='rq-card'>"
            f"<div class='rq-card-title'>Operational Category</div>"
            f"<div class='rq-card-value'>{assessment.category}</div>"
            f"<div class='rq-card-subtext'>Score {assessment.score:.1f} out of 100. This combines weather, rainfall, drought, alerts, and station conditions.</div>"
            "<div style='margin-top:0.85rem'><b>Main drivers</b><ul class='rq-list'>"
            f"{driver_html}</ul></div>"
            "<div style='margin-top:0.65rem'><b>Recommended actions</b><ul class='rq-list'>"
            f"{action_html}</ul></div>"
            f"<div class='rq-inline-note' style='margin-top:0.8rem'>{html.escape(assessment.disclaimer)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_station_cards(status_df: pd.DataFrame) -> None:
    if status_df.empty:
        st.info("No station status records are available.")
        return

    columns = st.columns(min(3, len(status_df)))
    for idx, row in enumerate(status_df.itertuples(index=False)):
        with columns[idx % len(columns)]:
            badges = [highlight_badge("success" if row.status == "ONLINE" else "warning", row.status)]
            if row.low_battery:
                badges.append(highlight_badge("warning", "LOW BATTERY"))
            if row.low_signal:
                badges.append(highlight_badge("warning", "LOW SIGNAL"))
            if row.sensor_error:
                badges.append(highlight_badge("critical", "SENSOR ERROR"))
            render_signal_card(
                title=f"{row.station_name}",
                value=format_number(row.air_temp_f, " F", 1),
                subtitle=(
                    f"{row.pasture_id} | Battery {format_number(row.battery_voltage, 'V', 2)} | "
                    f"Tank {format_number(row.water_tank_pct, '%', 0)}"
                ),
                badges=badges,
            )


theme = get_theme(st.session_state.theme_mode)
apply_app_theme(theme)

with st.sidebar:
    st.radio("Color Mode", options=["High Plains Day", "Mesquite Night"], key="theme_mode", horizontal=True)
    st.header("Scenario")
    uploaded_boundary = st.file_uploader("Upload ranch or pasture boundary", type=["geojson", "json", "kml", "kmz"])
    st.slider("Weekly modeling window", min_value=12, max_value=104, step=2, key="weeks")
    st.slider("Vegetation history (years)", min_value=5, max_value=10, key="history_years")
    st.number_input("Scenario seed", min_value=1, step=1, key="seed")
    st.caption("RangeIQ stays runnable offline. Upload a GeoJSON, JSON, KML, or KMZ boundary file to replace the placeholder pasture immediately.")

runtime_settings = build_runtime_settings()
uploaded_boundary_name = uploaded_boundary.name if uploaded_boundary is not None else None
uploaded_boundary_bytes = uploaded_boundary.getvalue() if uploaded_boundary is not None else None
saved_boundary_name, saved_boundary_bytes, saved_boundary_mode = load_saved_boundary_from_state(PERSISTED_DASHBOARD_STATE)
effective_boundary_name = uploaded_boundary_name or saved_boundary_name
effective_boundary_bytes = uploaded_boundary_bytes if uploaded_boundary_bytes is not None else saved_boundary_bytes
boundary_mode = "uploaded" if uploaded_boundary_name is not None else saved_boundary_mode
boundary_uploaded = boundary_mode in {"uploaded", "saved"}
geojson_text = (
    effective_boundary_bytes.decode("utf-8")
    if effective_boundary_name is not None and effective_boundary_bytes is not None and Path(effective_boundary_name).suffix.lower() in {".geojson", ".json"}
    else None
)
artifacts = load_artifacts(
    runtime_settings=runtime_settings,
    geojson_text=geojson_text,
    uploaded_boundary_name=effective_boundary_name,
    uploaded_boundary_bytes=effective_boundary_bytes,
    weeks=int(st.session_state.weeks),
    history_years=int(st.session_state.history_years),
    seed=int(st.session_state.seed),
)

latest_snapshot = artifacts.latest_snapshot.copy()
latest_snapshot["week_start"] = pd.to_datetime(latest_snapshot["week_start"])
history_df = artifacts.vegetation_history.copy()
history_df["month_start"] = pd.to_datetime(history_df["month_start"])
vegetation_artifacts = artifacts.public_data_bundle.vegetation_artifacts
vegetation_summary_df = vegetation_artifacts.summary_frame.copy() if vegetation_artifacts is not None else pd.DataFrame()
vegetation_ndvi_df = vegetation_artifacts.ndvi_series.copy() if vegetation_artifacts is not None else pd.DataFrame()
vegetation_cover_df = vegetation_artifacts.rap_cover_series.copy() if vegetation_artifacts is not None else pd.DataFrame()
vegetation_production_df = vegetation_artifacts.rap_production_series.copy() if vegetation_artifacts is not None else pd.DataFrame()
if not vegetation_ndvi_df.empty:
    if "month_start" in vegetation_ndvi_df.columns:
        vegetation_ndvi_df["month_start"] = pd.to_datetime(vegetation_ndvi_df["month_start"])
    elif "date" in vegetation_ndvi_df.columns:
        vegetation_ndvi_df["month_start"] = pd.to_datetime(vegetation_ndvi_df["date"]).dt.to_period("M").dt.to_timestamp()
weather_bundle = load_weather_bundle_cached(
    runtime_settings=runtime_settings,
    lat=runtime_settings.ranch.latitude,
    lon=runtime_settings.ranch.longitude,
    provider=runtime_settings.weather.provider,
    refresh_bucket=_refresh_bucket(runtime_settings.weather.refresh_minutes),
)
alert_bundle = load_alert_bundle_cached(
    runtime_settings=runtime_settings,
    lat=runtime_settings.ranch.latitude,
    lon=runtime_settings.ranch.longitude,
    provider=runtime_settings.alerts.provider,
    refresh_bucket=_refresh_bucket(runtime_settings.alerts.refresh_minutes),
)

fire_assessment = assess_fire_risk(
    current_weather=WeatherService.current_as_dict(weather_bundle),
    alerts_df=alert_bundle.alerts,
    latest_snapshot=latest_snapshot,
    sensor_status_df=pd.DataFrame(),
    sensor_readings_df=pd.DataFrame(),
    app_settings=runtime_settings,
)

selected_pasture_default = latest_snapshot["pasture_id"].iloc[0]
if st.session_state.get("selected_pasture") not in set(latest_snapshot["pasture_id"]):
    st.session_state.selected_pasture = selected_pasture_default

selected_pasture = st.session_state.selected_pasture
selected_pasture_name = latest_snapshot.loc[latest_snapshot["pasture_id"] == selected_pasture, "name"].iloc[0]
current_weather = weather_bundle.current
last_updated = max(weather_bundle.loaded_at, alert_bundle.loaded_at, artifacts.public_data_bundle.loaded_at)
total_acres = float(latest_snapshot["acres"].sum()) if "acres" in latest_snapshot.columns else 0.0
pasture_count = int(len(latest_snapshot))
provider_modes = [weather_bundle.mode, alert_bundle.mode] + [status.mode for status in artifacts.public_data_bundle.source_status]
provider_fallback_active = any(mode.endswith("fallback-mock") or mode == "stale-cache" for mode in provider_modes)
action_pastures = latest_snapshot.loc[
    latest_snapshot["recommendation"].isin(["SUPPLEMENT", "REDUCE STOCKING", "DESTOCK WARNING"])
].copy()
vegetation_source_status = next(
    (status for status in artifacts.public_data_bundle.source_status if status.component == "Vegetation"),
    None,
)

header_logo_col, header_meta_col = st.columns([1.05, 1], gap="medium")
with header_logo_col:
    logo_path = get_logo_path(st.session_state.theme_mode)
    if logo_path.exists():
        st.image(str(logo_path), width=360)
with header_meta_col:
    render_dashboard_header(
        runtime_settings=runtime_settings,
        last_updated=last_updated,
        total_acres=total_acres,
        pasture_count=pasture_count,
        boundary_mode=boundary_mode,
        map_basemap=st.session_state.map_basemap,
    )

home_tab, sensors_tab, sensor_network_tab, pastures_tab, data_tab, settings_tab = st.tabs(
    ["Home", "Sensors", "Sensor Network", "Pastures", "Data", "Settings"]
)

with home_tab:
    if boundary_mode == "default":
        st.info("The default ranch boundary is the single Caja Caliente pasture drawn from your provided Alpine property corners.")
    elif boundary_mode == "saved":
        st.info("RangeIQ loaded your last saved ranch boundary automatically. Upload a new file or save again if you want to replace it.")

    if provider_fallback_active:
        st.warning("One or more public-data providers failed in this run. RangeIQ automatically fell back to mock data to keep the dashboard operational.")

    top_metrics = st.columns(4)
    top_metrics[0].metric("Current Temp", format_number(current_weather.temperature_f, " F", 1), f"Feels like {format_number(current_weather.feels_like_f, ' F', 1)}")
    top_metrics[1].metric("Wind", format_number(current_weather.wind_speed_mph, " mph", 1), f"Gust {format_number(current_weather.wind_gust_mph, ' mph', 1)}")
    top_metrics[2].metric("Fire Risk", f"{fire_assessment.category}", f"Score {fire_assessment.score:.1f}")
    top_metrics[3].metric("Pastures", f"{pasture_count}", f"{total_acres:,.1f} acres")

    weather_col, forecast_col = st.columns([1, 1.2], gap="medium")
    with weather_col:
        st.subheader("Current Weather")
        st.caption(f"{current_weather.weather_label} | Source: {current_weather.source}")
        weather_metrics_a = st.columns(2)
        weather_metrics_b = st.columns(2)
        weather_metrics_c = st.columns(2)
        weather_metrics_a[0].metric("Temperature", format_number(current_weather.temperature_f, " F", 1))
        weather_metrics_a[1].metric("Feels Like", format_number(current_weather.feels_like_f, " F", 1))
        weather_metrics_b[0].metric("Humidity", format_number(current_weather.humidity_pct, "%", 0))
        weather_metrics_b[1].metric("Precip Chance", format_number(current_weather.precip_probability_pct, "%", 0))
        weather_metrics_c[0].metric("Wind Dir", current_weather.wind_direction or "--")
        weather_metrics_c[1].metric("Rain Today", format_number(current_weather.rainfall_expected_today_in, " in", 2))
        st.caption(
            f"Observation time: {format_timestamp(current_weather.observation_time)} | "
            f"Wind gust: {format_number(current_weather.wind_gust_mph, ' mph', 1)}"
        )

    with forecast_col:
        st.subheader("7-Day Forecast")
        st.dataframe(prepare_forecast_table(weather_bundle.forecast), width="stretch", hide_index=True)

    risk_col, alert_col = st.columns([1, 1.15], gap="medium")
    with risk_col:
        st.plotly_chart(plot_fire_risk_gauge(fire_assessment.score, fire_assessment.category, fire_assessment.color, theme), width="stretch")
        render_fire_risk_panel(fire_assessment)
    with alert_col:
        render_alert_panel(alert_bundle.alerts)

    map_col, summary_col = st.columns([1.18, 0.92], gap="medium")
    with map_col:
        st.subheader("Ranch Map")
        render_pasture_map(latest_snapshot, theme, st.session_state.map_basemap)
        st.caption(
            "USGS NAIP aerial imagery is now the default ranch map when internet is available. "
            "If imagery is unavailable, RangeIQ falls back to the standard map. Plain always keeps the pasture outline visible offline."
        )

    with summary_col:
        st.subheader("Pasture Summary")
        st.dataframe(
            latest_snapshot[
                [
                    "pasture_id",
                    "name",
                    "acres",
                    "pasture_condition_score",
                    "predicted_forage_score",
                    "rainfall_deficit_30d",
                    "drought_category",
                    "grazing_pressure",
                    "water_risk_score",
                    "stocking_risk_score",
                    "recommendation",
                ]
            ].sort_values(["stocking_risk_score", "water_risk_score"], ascending=[False, False]),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Recommendations Summary")
    if action_pastures.empty:
        st.success("No pastures currently require supplement, reduced stocking, or destocking action in this scenario.")
    else:
        st.dataframe(
            action_pastures[
                [
                    "pasture_id",
                    "name",
                    "pasture_condition_score",
                    "predicted_forage_score",
                    "grazing_pressure",
                    "water_risk_score",
                    "stocking_risk_score",
                    "recommendation",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

with sensors_tab:
    render_under_development_notice(
        "Sensors",
        "We paused live station monitoring while we optimize dashboard performance and finish the next sensor architecture pass.",
    )

with sensor_network_tab:
    render_under_development_notice(
        "Sensor Network",
        "Meshtastic and remote-station ingestion are still in progress, so the hosted app is not loading that stack right now.",
    )

with pastures_tab:
    selector_cols = st.columns([1, 1.3])
    with selector_cols[0]:
        st.selectbox(
            "Pasture detail",
            options=latest_snapshot["pasture_id"].tolist(),
            key="selected_pasture",
            format_func=lambda pasture_id: f"{pasture_id} - {latest_snapshot.loc[latest_snapshot['pasture_id'] == pasture_id, 'name'].iloc[0]}",
        )
    with selector_cols[1]:
        selected_pasture_name = latest_snapshot.loc[latest_snapshot["pasture_id"] == st.session_state.selected_pasture, "name"].iloc[0]
        st.caption(f"Selected pasture: {selected_pasture_name}")

    selected_pasture = st.session_state.selected_pasture

    pasture_metrics = latest_snapshot.loc[latest_snapshot["pasture_id"] == selected_pasture].iloc[0]
    pasture_metric_cols = st.columns(5)
    pasture_metric_cols[0].metric("Condition Score", format_number(pasture_metrics["pasture_condition_score"], "", 1))
    pasture_metric_cols[1].metric("Forage Score", format_number(pasture_metrics["predicted_forage_score"], "", 1))
    pasture_metric_cols[2].metric("Rainfall Deficit", format_number(pasture_metrics["rainfall_deficit_30d"], " mm", 1))
    pasture_metric_cols[3].metric("Grazing Pressure", format_number(pasture_metrics["grazing_pressure"], "", 3))
    pasture_metric_cols[4].metric("Recommendation", str(pasture_metrics["recommendation"]))

    st.dataframe(
        latest_snapshot[
            [
                "pasture_id",
                "name",
                "pasture_condition_score",
                "predicted_forage_score",
                "grazing_pressure",
                "rainfall_deficit_30d",
                "drought_category",
                "water_risk_score",
                "stocking_risk_score",
                "recommendation",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

    pasture_chart_a, pasture_chart_b = st.columns(2, gap="medium")
    with pasture_chart_a:
        st.plotly_chart(
            apply_chart_theme(plot_condition_scores(latest_snapshot, theme["recommendation_colors"]), theme),
            width="stretch",
        )
    with pasture_chart_b:
        st.plotly_chart(
            apply_chart_theme(plot_water_vs_stocking_risk(latest_snapshot, theme["recommendation_colors"]), theme),
            width="stretch",
        )

    st.subheader("Vegetation History / Range Health")
    selected_vegetation = (
        vegetation_summary_df.loc[vegetation_summary_df["pasture_id"] == selected_pasture].iloc[0]
        if not vegetation_summary_df.empty and selected_pasture in set(vegetation_summary_df["pasture_id"])
        else None
    )
    if selected_vegetation is not None:
        ndvi_anomaly_percent_value = pd.to_numeric(selected_vegetation.get("ndvi_anomaly_percent"), errors="coerce")
        ndvi_badge_level = "info" if pd.isna(ndvi_anomaly_percent_value) else ("success" if float(ndvi_anomaly_percent_value) >= 0 else "warning")
        st.caption(
            f"NDVI source: {selected_vegetation.get('ndvi_source_label', 'Earth Search STAC / Sentinel-2')} | "
            "RAP source: Rangeland Analysis Platform"
        )
        vegetation_card_cols = st.columns(4, gap="medium")
        with vegetation_card_cols[0]:
            render_signal_card(
                title="Current Greenness",
                value=format_number(selected_vegetation["ndvi_latest"], "", 3),
                subtitle=(
                    f"{friendly_ndvi_status(selected_vegetation['ndvi_status'])} | "
                    f"Anomaly {format_number(selected_vegetation['ndvi_anomaly_percent'], '%', 1)}"
                ),
                badges=[highlight_badge(ndvi_badge_level, str(selected_vegetation["ndvi_status"]).upper())],
            )
        with vegetation_card_cols[1]:
            render_signal_card(
                title="Perennial Grass",
                value=friendly_trend_label(selected_vegetation["rap_perennial_grass_trend"]),
                subtitle="Long-term rangeland structure",
                badges=[highlight_badge("success" if selected_vegetation["rap_perennial_grass_trend"] == "increasing" else "warning" if selected_vegetation["rap_perennial_grass_trend"] == "declining" else "info", str(selected_vegetation["rap_perennial_grass_trend"]).upper())],
            )
        with vegetation_card_cols[2]:
            render_signal_card(
                title="Bare Ground",
                value=friendly_trend_label(selected_vegetation["rap_bare_ground_trend"]),
                subtitle="Watch for exposed soil moving higher over time",
                badges=[highlight_badge("warning" if selected_vegetation["rap_bare_ground_trend"] == "increasing" else "success" if selected_vegetation["rap_bare_ground_trend"] == "declining" else "info", str(selected_vegetation["rap_bare_ground_trend"]).upper())],
            )
        with vegetation_card_cols[3]:
            render_signal_card(
                title="RangeIQ Veg Score",
                value=f"{format_number(selected_vegetation['rangeiq_vegetation_score'], '', 0)} {str(selected_vegetation['rangeiq_vegetation_category']).upper()}",
                subtitle=str(selected_vegetation["rangeiq_vegetation_explanation"]),
                badges=[highlight_badge("success" if str(selected_vegetation["rangeiq_vegetation_category"]) in {"Excellent", "Good"} else "warning" if str(selected_vegetation["rangeiq_vegetation_category"]) in {"Watch", "Stressed"} else "critical", str(selected_vegetation["rangeiq_vegetation_category"]).upper())],
            )

        if str(selected_vegetation.get("rangeiq_vegetation_drivers", "")).strip():
            st.caption(f"Main drivers: {selected_vegetation['rangeiq_vegetation_drivers']}")
        if str(selected_vegetation.get("vegetation_warnings", "")).strip():
            st.warning(selected_vegetation["vegetation_warnings"])
    else:
        st.info("Vegetation history is not available for the selected pasture in this run.")

    vegetation_chart_a, vegetation_chart_b = st.columns(2, gap="medium")
    with vegetation_chart_a:
        if not vegetation_ndvi_df.empty:
            st.plotly_chart(apply_chart_theme(plot_public_ndvi_history(vegetation_ndvi_df, selected_pasture), theme), width="stretch")
        else:
            st.info("NDVI history is unavailable for this pasture.")
    with vegetation_chart_b:
        if not vegetation_cover_df.empty:
            st.plotly_chart(apply_chart_theme(plot_rap_cover_history(vegetation_cover_df, selected_pasture), theme), width="stretch")
        else:
            st.info("RAP cover history is unavailable for this pasture.")

    vegetation_chart_c, vegetation_chart_d = st.columns(2, gap="medium")
    with vegetation_chart_c:
        if not vegetation_production_df.empty:
            st.plotly_chart(apply_chart_theme(plot_rap_production_history(vegetation_production_df, selected_pasture), theme), width="stretch")
        else:
            st.info("RAP production history is unavailable for this pasture.")
    with vegetation_chart_d:
        st.plotly_chart(apply_chart_theme(plot_rainfall_deficit_history(history_df, selected_pasture), theme), width="stretch")

    pasture_chart_e, pasture_chart_f = st.columns(2, gap="medium")
    with pasture_chart_e:
        st.plotly_chart(apply_chart_theme(plot_ndvi_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")
    with pasture_chart_f:
        st.plotly_chart(apply_chart_theme(plot_forage_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")

    pasture_chart_g, pasture_chart_h = st.columns(2, gap="medium")
    with pasture_chart_g:
        st.plotly_chart(apply_chart_theme(plot_rainfall_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")
    with pasture_chart_h:
        st.plotly_chart(
            apply_chart_theme(plot_recommendation_mix(latest_snapshot, theme["recommendation_colors"]), theme),
            width="stretch",
        )

with data_tab:
    source_card_cols = st.columns(4)
    with source_card_cols[0]:
        render_signal_card(
            title="Weather Source",
            value=weather_bundle.provider_name.upper(),
            subtitle=weather_bundle.source_message,
            badges=[status_badge(weather_bundle.mode)],
        )
    with source_card_cols[1]:
        render_signal_card(
            title="Alert Source",
            value=alert_bundle.provider_name.upper(),
            subtitle=alert_bundle.source_message,
            badges=[status_badge(alert_bundle.mode)],
        )
    with source_card_cols[2]:
        vegetation_value = runtime_settings.public_data.vegetation.provider.upper()
        vegetation_subtitle = (
            "Vegetation history combines Earth Search STAC NDVI with RAP."
            if vegetation_source_status is None
            else vegetation_source_status.status
        )
        vegetation_badge = status_badge("mock" if vegetation_source_status is None else vegetation_source_status.mode)
        render_signal_card(
            title="Vegetation Source",
            value=vegetation_value if vegetation_source_status is None else vegetation_source_status.active_provider.upper(),
            subtitle=vegetation_subtitle,
            badges=[vegetation_badge],
        )
    with source_card_cols[3]:
        boundary_value = "DEFAULT CORNERS"
        boundary_badge = highlight_badge("info", "DEFAULT")
        boundary_subtitle = "Default ranch geometry comes from your provided Alpine property corners."
        if boundary_mode == "uploaded":
            boundary_value = "UPLOADED"
            boundary_badge = highlight_badge("success", "UPLOADED")
            boundary_subtitle = "This run is using the boundary file you uploaded in the current session."
        elif boundary_mode == "saved":
            boundary_value = "SAVED"
            boundary_badge = highlight_badge("success", "SAVED")
            boundary_subtitle = "This run is using the last boundary file you saved for future launches."
        render_signal_card(
            title="Boundary Mode",
            value=boundary_value,
            subtitle=boundary_subtitle,
            badges=[boundary_badge],
        )

    st.subheader("Public Data Source Status")
    provider_rows = [
        {
            "Component": "Weather",
            "Configured provider": runtime_settings.weather.provider,
            "Active provider": weather_bundle.provider_name,
            "Mode": weather_bundle.mode,
            "Status": weather_bundle.source_message,
            "Last updated": format_timestamp(weather_bundle.loaded_at),
            "Citation": "https://www.weather.gov/documentation/services-web-api",
        },
        {
            "Component": "Alerts",
            "Configured provider": runtime_settings.alerts.provider,
            "Active provider": alert_bundle.provider_name,
            "Mode": alert_bundle.mode,
            "Status": alert_bundle.source_message,
            "Last updated": format_timestamp(alert_bundle.loaded_at),
            "Citation": "https://www.weather.gov/documentation/services-web-api",
        },
        {
            "Component": "Sensors",
            "Configured provider": "under_development",
            "Active provider": "under_development",
            "Mode": "paused",
            "Status": "Sensor monitoring is temporarily disabled in the hosted dashboard while performance work continues.",
            "Last updated": format_timestamp(last_updated),
            "Citation": "under development",
        },
        {
            "Component": "Sensor Network",
            "Configured provider": "under_development",
            "Active provider": "under_development",
            "Mode": "paused",
            "Status": "Meshtastic / LoRa network pages are paused in the hosted app while the rest of RangeIQ is optimized.",
            "Last updated": format_timestamp(last_updated),
            "Citation": "under development",
        },
    ]
    provider_rows.extend(
        [
            {
                "Component": status.component,
                "Configured provider": status.configured_provider,
                "Active provider": status.active_provider,
                "Mode": status.mode,
                "Status": status.status,
                "Last updated": format_timestamp(status.loaded_at),
                "Citation": status.citation_url,
            }
            for status in artifacts.public_data_bundle.source_status
        ]
    )
    provider_rows.extend(
        [
            {
                "Component": "Pasture MVP",
                "Configured provider": "synthetic",
                "Active provider": "synthetic",
                "Mode": "synthetic",
                "Status": "Synthetic pasture-week model pipeline remains active underneath the operational dashboard.",
                "Last updated": format_timestamp(last_updated),
                "Citation": "synthetic MVP pipeline",
            },
            {
                "Component": "ML Training Dataset",
                "Configured provider": "hybrid",
                "Active provider": f"{artifacts.training_dataset_summary['public_feature_count']} public features",
                "Mode": "hybrid",
                "Status": (
                    f"{artifacts.training_dataset_summary['rows']} rows across "
                    f"{artifacts.training_dataset_summary['pastures']} pasture(s) and "
                    f"{artifacts.training_dataset_summary['weeks']} week(s)."
                ),
                "Last updated": format_timestamp(last_updated),
                "Citation": "RangeIQ hybrid training dataset",
            },
        ]
    )
    provider_rows = pd.DataFrame(provider_rows)
    st.dataframe(provider_rows, width="stretch", hide_index=True)

    sensor_path = Path(runtime_settings.sensors.csv_path)
    file_rows = pd.DataFrame(
        [
            {"Path": str(runtime_settings.default_weekly_output_path), "Exists": Path(runtime_settings.default_weekly_output_path).exists()},
            {"Path": str(runtime_settings.default_scored_output_path), "Exists": Path(runtime_settings.default_scored_output_path).exists()},
            {"Path": str(runtime_settings.default_history_output_path), "Exists": Path(runtime_settings.default_history_output_path).exists()},
            {"Path": str(runtime_settings.default_monthly_report_csv_path), "Exists": Path(runtime_settings.default_monthly_report_csv_path).exists()},
            {"Path": str(runtime_settings.default_monthly_report_md_path), "Exists": Path(runtime_settings.default_monthly_report_md_path).exists()},
        ]
    )
    st.subheader("File Status")
    st.dataframe(file_rows, width="stretch", hide_index=True)

    st.subheader("Mock / Real Mode Indicator")
    st.json(
        {
            "workspace_id": CURRENT_WORKSPACE_ID,
            "account_email": CURRENT_USER.email,
            "weather_mode": weather_bundle.mode,
            "alerts_mode": alert_bundle.mode,
            "sensors_mode": "under_development",
            "sensor_network_mode": "under_development",
            "public_data_modes": {status.component: status.mode for status in artifacts.public_data_bundle.source_status},
            "boundary_mode": boundary_mode if boundary_mode != "default" else runtime_settings.boundary_status,
            "units": runtime_settings.ranch.units,
        }
    )

    st.subheader("Hybrid Training Dataset Summary")
    st.json(artifacts.training_dataset_summary)

    st.subheader("Monthly Ranch Report")
    st.markdown(artifacts.monthly_report_markdown)
    st.download_button(
        "Download CSV report",
        data=artifacts.monthly_report_table.to_csv(index=False).encode("utf-8"),
        file_name="rangeiq_monthly_report.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download Markdown report",
        data=artifacts.monthly_report_markdown.encode("utf-8"),
        file_name="rangeiq_monthly_report.md",
        mime="text/markdown",
    )

with settings_tab:
    st.subheader("Account")
    account_cols = st.columns([1.2, 1.2, 0.8], gap="medium")
    with account_cols[0]:
        st.markdown(f"**Signed in as**  \n{CURRENT_USER.full_name}")
        st.caption(CURRENT_USER.email)
    with account_cols[1]:
        st.markdown(f"**Private workspace**  \n`{CURRENT_WORKSPACE_ID}`")
        st.caption("This account's ranch files and saved settings reopen here after login.")
    with account_cols[2]:
        st.write("")
        st.write("")
        if st.button("Log Out"):
            sign_out_user()
            st.rerun()

    st.subheader("Ranch Settings")
    ranch_cols = st.columns(2)
    ranch_cols[0].text_input("Ranch Name", key="ranch_name")
    ranch_cols[1].text_input("Ranch Address", key="ranch_address")
    ranch_cols = st.columns(3)
    ranch_cols[0].number_input("Latitude", format="%.6f", key="ranch_lat")
    ranch_cols[1].number_input("Longitude", format="%.6f", key="ranch_lon")
    ranch_cols[2].text_input("Timezone", key="ranch_timezone")
    st.selectbox("Units", options=["imperial"], key="ranch_units")
    st.selectbox(
        "Map Basemap",
        options=list(MAP_BASEMAP_LABELS.keys()),
        key="map_basemap",
        format_func=lambda value: MAP_BASEMAP_LABELS[value],
    )
    st.caption(
        "USGS NAIP aerial imagery is the best free ranch-view option for small Texas properties. "
        "Plain keeps the ranch polygon visible even when you are offline."
    )

    st.subheader("Provider Settings")
    provider_cols = st.columns(2)
    provider_cols[0].selectbox("Weather Provider", options=["mock", "nws", "openmeteo"], key="weather_provider")
    provider_cols[1].selectbox("Alert Provider", options=["mock", "nws"], key="alerts_provider")
    st.caption("Sensor provider settings are temporarily hidden while the sensor stack is under development.")

    st.subheader("Public Data Providers")
    public_provider_cols = st.columns(3)
    public_provider_cols[0].selectbox("Historical Weather", options=["mock", "nasa_power"], key="historical_weather_provider")
    public_provider_cols[1].selectbox("Soils", options=["mock", "usda_sda"], key="soils_provider")
    public_provider_cols[2].selectbox("Drought", options=["mock", "usdm"], key="drought_provider")
    cache_cols = st.columns(5)
    cache_cols[0].toggle("Enable Public Cache", key="public_cache_enabled")
    cache_cols[1].number_input("Weather Refresh (h)", min_value=1, step=12, key="historical_weather_refresh_hours")
    cache_cols[2].number_input("Soils Refresh (h)", min_value=1, step=24, key="soils_refresh_hours")
    cache_cols[3].number_input("Drought Refresh (h)", min_value=1, step=12, key="drought_refresh_hours")
    cache_cols[4].number_input("Vegetation Refresh (h)", min_value=1, step=24, key="vegetation_refresh_hours")
    public_provider_cols = st.columns(1)
    public_provider_cols[0].selectbox("Vegetation", options=["mock", "earth_search_stac", "climate_engine"], key="vegetation_provider")
    st.caption(
        "Public historical sources are cached on disk so RangeIQ can reuse them offline and avoid unnecessary refreshes. "
        "Vegetation history now combines Earth Search STAC NDVI with RAP. Earth Search STAC is the default live NDVI source, "
        "and Climate Engine remains optional. If live vegetation providers fail, RangeIQ falls back to mock history."
    )

    st.subheader("Sensors")
    st.info(
        "Sensor monitoring and sensor-network controls are currently under development. "
        "They are paused in the hosted dashboard while we improve performance and finish the next implementation pass."
    )

    st.subheader("Fire Risk Thresholds")
    fire_cols = st.columns(3)
    fire_cols[0].number_input("High Wind (mph)", min_value=5, step=1, key="high_wind_mph")
    fire_cols[1].number_input("High Gust (mph)", min_value=10, step=1, key="high_gust_mph")
    fire_cols[2].number_input("Low Humidity (%)", min_value=5, max_value=60, step=1, key="low_humidity_pct")
    fire_cols = st.columns(3)
    fire_cols[0].number_input("High Temperature (F)", min_value=60, max_value=120, step=1, key="high_temperature_f")
    fire_cols[1].number_input("Low Rainfall 7d (in)", min_value=0.0, max_value=2.0, step=0.01, format="%.2f", key="low_rainfall_7d_in")
    fire_cols[2].number_input("Low Soil Moisture (%)", min_value=1, max_value=50, step=1, key="low_soil_moisture_pct")

    st.subheader("Save This Setup")
    st.caption(
        "Save writes your current ranch settings to `config.yaml` and remembers the current uploaded boundary file "
        "so RangeIQ can reopen with the same setup next time."
    )
    save_cols = st.columns([1, 2], gap="medium")
    with save_cols[0]:
        if st.button("Save Current Setup"):
            current_runtime_settings = build_runtime_settings()
            target_workspace_id = CURRENT_WORKSPACE_ID
            st.query_params["workspace"] = target_workspace_id
            dashboard_state_payload = build_dashboard_state_payload(
                current_runtime_settings,
                workspace_id=target_workspace_id,
                boundary_filename=effective_boundary_name,
                boundary_bytes=effective_boundary_bytes,
                existing_state=PERSISTED_DASHBOARD_STATE,
            )
            saved_state_path = save_dashboard_state(
                dashboard_state_payload,
                path=current_runtime_settings.workspace_state_path_for(target_workspace_id),
            )
            updated_user = AUTH_SERVICE.update_user_profile(
                CURRENT_USER.user_id,
                ranch_name=current_runtime_settings.ranch.name,
                ranch_address=current_runtime_settings.ranch.address,
                ranch_latitude=current_runtime_settings.ranch.latitude,
                ranch_longitude=current_runtime_settings.ranch.longitude,
            )
            sign_in_user(updated_user)
            saved_boundary_notice = "No custom boundary was saved; RangeIQ will reopen on the default corners."
            if dashboard_state_payload.get("saved_boundary", {}).get("path"):
                saved_boundary_notice = (
                    f"Saved boundary file: {dashboard_state_payload['saved_boundary']['filename']}"
                )
            st.success(
                f"Account settings saved to {saved_state_path}. {saved_boundary_notice} "
                "Log back into this account later to reopen the same ranch setup."
            )
    with save_cols[1]:
        boundary_save_mode = "current upload" if boundary_mode == "uploaded" else "saved boundary" if boundary_mode == "saved" else "default corners"
        st.markdown(
            f"Current workspace: **{CURRENT_WORKSPACE_ID}**. "
            f"Reopen state: **{boundary_save_mode}**. "
            "Providers, ranch name/address/GPS, map settings, time horizon, and thresholds are saved to this account."
        )

    st.subheader("Current Effective Config")
    preview_settings = build_runtime_settings()
    st.json(preview_settings.to_display_dict())

with st.expander("Model metrics"):
    st.write(f"Selected forage regressor: `{artifacts.selected_forage_model}`")
    st.json(artifacts.model_metrics["forage_model"])
    st.text(artifacts.model_metrics["stress_model"]["report"])
