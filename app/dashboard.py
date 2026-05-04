from __future__ import annotations

import calendar
import base64
import copy
import html
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
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
from ranch_ai.features.feedback_dataset import (
    build_feedback_calibration_dataset,
    build_feedback_dataset,
    build_feedback_shadow_review_dataset,
    summarize_feedback_shadow_review_dataset,
    summarize_feedback_calibration_dataset,
    summarize_feedback_dataset,
)
from ranch_ai.models.ranch_domain import (
    FEEDBACK_CONFIDENCE_OPTIONS,
    FEEDBACK_LABEL_TYPE_OPTIONS,
    FEEDBACK_VALUE_OPTIONS,
    LIVESTOCK_SPECIES_OPTIONS,
    MANAGEMENT_STYLE_OPTIONS,
    MANAGEMENT_UNIT_TYPE_OPTIONS,
    RANCH_GOAL_OPTIONS,
    RANCH_TYPE_OPTIONS,
    UNIT_ACTIVITY_TYPE_OPTIONS,
    ManagementUnit,
    ManagementUnitOverride,
    UnitFeedbackLabel,
    LivestockGroup,
    RanchProfile,
    UnitActivityEvent,
    UnitActivitySummary,
    attach_activity_summaries,
    attach_utilization_summaries,
    build_management_units,
    build_livestock_group_load_summaries,
    build_operation_planner_suggestions,
    build_unit_activity_summary_lookup,
    build_unit_utilization_summaries,
    coerce_management_unit_overrides,
    coerce_unit_feedback_labels,
    coerce_unit_activity_events,
    coerce_livestock_groups,
    livestock_groups_frame,
    livestock_group_load_frame,
    management_units_frame,
    operation_planner_frame,
    OperationPlannerSuggestion,
    primary_livestock_group,
    serialize_unit_activity_events,
    serialize_unit_feedback_labels,
    serialize_livestock_groups,
    serialize_management_unit_overrides,
    unit_activity_frame,
    unit_feedback_frame,
    unit_utilization_frame,
    unit_term,
)
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

FIELD_SECTION_OPTIONS = [
    "Dashboard",
    "Management Units",
    "Vegetation & Land Health",
    "Livestock & Management",
    "Data & Providers",
    "Settings",
    "Sensors",
]

FIELD_SECTION_SHORT_LABELS = {
    "Dashboard": "Map & Alerts",
    "Management Units": "Units",
    "Vegetation & Land Health": "Land Health",
    "Livestock & Management": "Livestock",
    "Data & Providers": "Data",
    "Settings": "Settings",
    "Sensors": "Sensors",
}

LEAFLET_BASEMAPS: dict[str, dict[str, Any]] = {
    "naip": {
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        "attribution": "USGS The National Map Imagery",
        "max_zoom": 20,
        "max_native_zoom": 16,
    },
    "satellite": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri World Imagery",
        "max_zoom": 20,
        "max_native_zoom": 18,
    },
    "road": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenStreetMap contributors",
        "max_zoom": 20,
        "subdomains": ["a", "b", "c"],
    },
    "light": {
        "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap contributors &copy; CARTO",
        "max_zoom": 20,
        "subdomains": ["a", "b", "c", "d"],
    },
    "dark": {
        "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap contributors &copy; CARTO",
        "max_zoom": 20,
        "subdomains": ["a", "b", "c", "d"],
    },
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
    "ranch_type": settings.ranch_profile.ranch_type,
    "management_style": settings.ranch_profile.management_style,
    "primary_goals": settings.ranch_profile.primary_goals,
    "rotates_animals": settings.ranch_profile.rotates_animals,
    "preferred_unit_term": settings.ranch_profile.preferred_unit_term,
    "default_unit_type": settings.ranch_profile.default_unit_type,
    "livestock_species": settings.ranch_profile.livestock_species,
    "ranch_profile_notes": settings.ranch_profile.notes,
    "livestock_groups": {},
    "map_basemap": "naip",
    "view_mode": "Desktop Workspace",
    "field_shell_section": "Dashboard",
    "selected_unit_id": "",
    "management_unit_overrides": {},
    "unit_activity_events": {},
    "unit_feedback_labels": {},
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


def apply_pre_auth_theme(theme: dict[str, object]) -> None:
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
            --rq-accent: {theme['accent']};
            --rq-accent-2: {theme['accent_2']};
        }}
        html, body {{
            color-scheme: light;
        }}
        .stApp {{
            background: {theme['app_background']};
            color: var(--rq-text);
            color-scheme: light;
        }}
        [data-testid="stAppViewContainer"] > .main .block-container {{
            max-width: 860px;
            padding-top: 2rem;
        }}
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu {{
            display: none !important;
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{
            color: var(--rq-text);
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"] > div,
        .stNumberInput div[data-baseweb="input"] > div,
        .stTextInput div[data-baseweb="input"] > div,
        .stTextInput div[data-baseweb="base-input"] > div,
        .stNumberInput div[data-baseweb="base-input"] > div,
        .stDateInput > div > div,
        .stTextArea textarea,
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input {{
            background: var(--rq-card) !important;
            border: 1px solid var(--rq-border) !important;
            color: var(--rq-text) !important;
            -webkit-text-fill-color: var(--rq-text) !important;
        }}
        .stButton > button,
        .stForm button {{
            background: linear-gradient(90deg, var(--rq-accent) 0%, var(--rq-accent-2) 100%);
            color: white !important;
            border: none !important;
            border-radius: 999px !important;
        }}
        [data-testid="stTabs"] button {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 999px;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            background: linear-gradient(135deg, var(--rq-accent) 0%, var(--rq-accent-2) 100%);
            border-color: transparent;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] p {{
            color: white !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def get_selected_unit_id(available_ids: list[str], default_unit_id: str) -> str:
    raw_value = st.query_params.get("unit", "")
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else ""
    requested = str(raw_value or "").strip()
    current = str(st.session_state.get("selected_unit_id", "") or "").strip()
    if requested in available_ids and requested != current:
        st.session_state.selected_unit_id = requested
        current = requested
    if current not in available_ids:
        st.session_state.selected_unit_id = default_unit_id
        current = default_unit_id
    if requested != current:
        st.query_params["unit"] = current
    return current


def get_management_unit_overrides() -> dict[str, ManagementUnitOverride]:
    raw_value = st.session_state.get("management_unit_overrides", {})
    overrides = coerce_management_unit_overrides(raw_value)
    st.session_state["management_unit_overrides"] = serialize_management_unit_overrides(overrides)
    return overrides


def get_livestock_groups() -> dict[str, LivestockGroup]:
    raw_value = st.session_state.get("livestock_groups", {})
    groups = coerce_livestock_groups(raw_value)
    st.session_state["livestock_groups"] = serialize_livestock_groups(groups)
    return groups


def get_unit_activity_events() -> dict[str, UnitActivityEvent]:
    raw_value = st.session_state.get("unit_activity_events", {})
    events = coerce_unit_activity_events(raw_value)
    st.session_state["unit_activity_events"] = serialize_unit_activity_events(events)
    return events


def get_unit_feedback_labels() -> dict[str, UnitFeedbackLabel]:
    raw_value = st.session_state.get("unit_feedback_labels", {})
    labels = coerce_unit_feedback_labels(raw_value)
    st.session_state["unit_feedback_labels"] = serialize_unit_feedback_labels(labels)
    return labels


def save_planner_suggestion_event(suggestion: OperationPlannerSuggestion) -> bool:
    updated_events = get_unit_activity_events()
    duplicate = next(
        (
            event
            for event in updated_events.values()
            if event.unit_id == suggestion.unit_id
            and event.activity_type == suggestion.suggested_activity_type
            and (event.livestock_group_id or "") == (suggestion.suggested_group_id or "")
            and event.start_date == suggestion.start_date
            and (event.end_date or "") == (suggestion.end_date or "")
        ),
        None,
    )
    if duplicate is not None:
        return False
    event_id = f"activity-{uuid4().hex[:10]}"
    updated_events[event_id] = UnitActivityEvent(
        event_id=event_id,
        unit_id=suggestion.unit_id,
        activity_type=suggestion.suggested_activity_type,
        livestock_group_id=suggestion.suggested_group_id,
        start_date=suggestion.start_date,
        end_date=suggestion.end_date,
        notes=f"Planned from RangeIQ suggestion. {suggestion.rationale}",
    )
    st.session_state["unit_activity_events"] = serialize_unit_activity_events(updated_events)
    return True


page_icon_path = ICON_PATH if ICON_PATH.exists() else FALLBACK_ICON_PATH
PAGE_ICON = Image.open(page_icon_path) if page_icon_path.exists() else None
st.set_page_config(page_title=f"{settings.app_name} | Operational Dashboard", page_icon=PAGE_ICON, layout="wide")
apply_pre_auth_theme(LIGHT_THEME)
AUTH_SERVICE = AuthService(settings.auth_db_path)
CURRENT_USER = render_auth_gate(AUTH_SERVICE)
CURRENT_WORKSPACE_ID = resolve_workspace_id(CURRENT_USER)
WORKSPACE_STATE_PATH = settings.workspace_state_path_for(CURRENT_WORKSPACE_ID)
PERSISTED_DASHBOARD_STATE = load_dashboard_state(WORKSPACE_STATE_PATH)
SESSION_DEFAULTS = session_defaults_for_state(PERSISTED_DASHBOARD_STATE, CURRENT_USER)
initialize_session_state(CURRENT_WORKSPACE_ID, SESSION_DEFAULTS)
st.session_state.setdefault("data_refresh_nonce", 0)


def load_artifacts(
    runtime_settings: Settings,
    geojson_text: str | None,
    uploaded_boundary_name: str | None,
    uploaded_boundary_bytes: bytes | None,
    weeks: int,
    history_years: int,
    seed: int,
    workspace_id: str | None,
    refresh_nonce: int = 0,
) -> MvpArtifacts:
    del refresh_nonce
    return run_mvp_pipeline(
        geojson_text=geojson_text,
        uploaded_boundary_name=uploaded_boundary_name,
        uploaded_boundary_bytes=uploaded_boundary_bytes,
        weeks=weeks,
        history_years=history_years,
        seed=seed,
        write_outputs=False,
        app_settings=runtime_settings,
        workspace_id=workspace_id,
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
    refresh_nonce: int,
):
    del refresh_bucket, refresh_nonce
    weather_service = WeatherService(runtime_settings)
    return weather_service.load_weather_bundle(lat=lat, lon=lon, provider=provider)


@st.cache_data(show_spinner=False, hash_funcs={Settings: _hash_settings}, max_entries=12)
def load_alert_bundle_cached(
    runtime_settings: Settings,
    lat: float,
    lon: float,
    provider: str,
    refresh_bucket: str,
    refresh_nonce: int,
):
    del refresh_bucket, refresh_nonce
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
        [data-testid="stFileUploader"] {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border-radius: 18px;
        }}
        [data-testid="stFileUploaderDropzone"] {{
            background: var(--rq-card) !important;
            border: 1px dashed var(--rq-border) !important;
            color: var(--rq-text) !important;
        }}
        [data-testid="stFileUploaderDropzone"] * {{
            color: var(--rq-text) !important;
        }}
        [data-testid="stFileUploaderFileName"] {{
            color: var(--rq-text) !important;
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"] > div,
        .stNumberInput div[data-baseweb="input"] > div,
        .stNumberInput div[data-baseweb="base-input"] > div,
        .stTextInput div[data-baseweb="input"] > div,
        .stTextInput div[data-baseweb="base-input"] > div,
        .stMultiSelect div[data-baseweb="select"] > div,
        .stDateInput > div > div,
        .stTextArea textarea,
        input,
        textarea,
        select,
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input,
        .stTextArea textarea,
        .stMultiSelect input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span {{
            background: var(--rq-card) !important;
            border: 1px solid var(--rq-border) !important;
            color: var(--rq-text) !important;
            -webkit-text-fill-color: var(--rq-text) !important;
            caret-color: var(--rq-text) !important;
            box-shadow: none !important;
        }}
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        textarea:-webkit-autofill,
        textarea:-webkit-autofill:hover,
        textarea:-webkit-autofill:focus,
        select:-webkit-autofill,
        select:-webkit-autofill:hover,
        select:-webkit-autofill:focus {{
            -webkit-text-fill-color: var(--rq-text) !important;
            caret-color: var(--rq-text) !important;
            -webkit-box-shadow: 0 0 0 1000px var(--rq-card) inset !important;
            box-shadow: 0 0 0 1000px var(--rq-card) inset !important;
            transition: background-color 9999s ease-in-out 0s !important;
        }}
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        .stDateInput input::placeholder,
        .stTextArea textarea::placeholder,
        .stMultiSelect input::placeholder,
        div[data-baseweb="base-input"] input::placeholder,
        div[data-baseweb="select"] input::placeholder {{
            color: var(--rq-muted) !important;
            -webkit-text-fill-color: var(--rq-muted) !important;
            opacity: 0.9 !important;
        }}
        div[data-baseweb="select"] svg,
        div[data-baseweb="base-input"] svg,
        .stDateInput svg,
        .stMultiSelect svg,
        .stNumberInput svg,
        .stTextInput svg {{
            fill: var(--rq-muted) !important;
            color: var(--rq-muted) !important;
        }}
        div[data-baseweb="select"] *:focus,
        div[data-baseweb="input"] *:focus,
        div[data-baseweb="base-input"] *:focus,
        .stTextArea textarea:focus,
        input:focus,
        textarea:focus,
        select:focus,
        .stTextInput input:focus,
        .stNumberInput input:focus,
        .stDateInput input:focus,
        .stMultiSelect input:focus {{
            border-color: var(--rq-accent-3) !important;
            box-shadow: 0 0 0 1px var(--rq-accent-3) !important;
        }}
        .stNumberInput button {{
            background: var(--rq-card) !important;
            border: 1px solid var(--rq-border) !important;
            color: var(--rq-text) !important;
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
        div[data-testid="stJson"],
        div[data-testid="stCodeBlock"] {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%) !important;
            border: 1px solid var(--rq-border) !important;
            border-radius: 18px !important;
            box-shadow: 0 10px 24px var(--rq-shadow);
            padding: 0.45rem !important;
        }}
        div[data-testid="stJson"] *,
        div[data-testid="stCodeBlock"] *,
        pre,
        code {{
            color: var(--rq-text) !important;
        }}
        div[data-testid="stJson"] pre,
        div[data-testid="stCodeBlock"] pre,
        pre {{
            background: var(--rq-card) !important;
        }}
        details {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 18px;
            box-shadow: 0 10px 24px var(--rq-shadow);
        }}
        details summary {{
            color: var(--rq-text) !important;
        }}
        .rq-card {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 20px;
            padding: 1rem 1.05rem;
            box-shadow: 0 10px 24px var(--rq-shadow);
        }}
        .rq-brand-banner {{
            display: grid;
            grid-template-columns: minmax(96px, 132px) 1fr;
            gap: 1rem;
            align-items: center;
            min-height: 100%;
        }}
        .rq-brand-mark {{
            display: flex;
            align-items: center;
            justify-content: center;
            background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.28), transparent 55%), var(--rq-card);
            border: 1px solid var(--rq-border);
            border-radius: 24px;
            min-height: 118px;
            padding: 0.8rem;
        }}
        .rq-brand-logo {{
            width: 100%;
            max-width: 108px;
            height: auto;
            object-fit: contain;
            filter: drop-shadow(0 8px 18px rgba(0,0,0,0.12));
        }}
        .rq-brand-copy {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
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
        .rq-brand-title {{
            color: var(--rq-accent);
            font-size: clamp(1.8rem, 2vw, 2.45rem);
            font-weight: 750;
            line-height: 1.02;
            margin-bottom: 0.3rem;
            text-wrap: balance;
        }}
        .rq-brand-meta {{
            color: var(--rq-muted);
            font-size: 0.94rem;
            line-height: 1.5;
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
        .rq-control-kicker {{
            color: var(--rq-muted);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.74rem;
            margin-bottom: 0.28rem;
        }}
        .rq-control-title {{
            color: var(--rq-accent);
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }}
        .rq-control-copy {{
            color: var(--rq-muted);
            font-size: 0.9rem;
            line-height: 1.45;
            margin-bottom: 0.7rem;
        }}
        .rq-section-intro {{
            color: var(--rq-muted);
            font-size: 0.95rem;
            line-height: 1.55;
            margin-bottom: 0.55rem;
        }}
        .rq-table-wrap {{
            background: linear-gradient(180deg, var(--rq-card) 0%, var(--rq-card-alt) 100%);
            border: 1px solid var(--rq-border);
            border-radius: 18px;
            box-shadow: 0 10px 24px var(--rq-shadow);
            overflow-x: auto;
            padding: 0.35rem;
        }}
        .rq-table {{
            width: 100%;
            border-collapse: collapse;
            color: var(--rq-text);
            font-size: 0.93rem;
        }}
        .rq-table th {{
            background: var(--rq-card-alt);
            color: var(--rq-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 0.74rem;
            text-align: left;
            padding: 0.75rem 0.7rem;
            border-bottom: 1px solid var(--rq-border);
        }}
        .rq-table td {{
            padding: 0.7rem;
            border-bottom: 1px solid color-mix(in srgb, var(--rq-border) 78%, transparent);
            color: var(--rq-text);
            vertical-align: top;
        }}
        .rq-table tr:last-child td {{
            border-bottom: none;
        }}
        @media (max-width: 980px) {{
            .rq-brand-banner {{
                grid-template-columns: 1fr;
            }}
            .rq-brand-mark {{
                min-height: 96px;
                max-width: 140px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_display_mode(view_mode: str) -> None:
    field_mode = view_mode == "Field Mode"
    field_css = ""
    if field_mode:
        field_css = """
        [data-testid='stAppViewContainer'] > .main .block-container { max-width: 920px; }
        .rq-field-intro { color: var(--rq-muted); font-size: 0.92rem; line-height: 1.45; margin: 0.1rem 0 0.6rem 0; }
        .rq-card-value { font-size: 1.45rem; }
        [data-testid='stMetric'] { padding: 12px 14px; }
        """
    st.markdown(
        f"""
        <style>
        [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            overflow-y: hidden !important;
            scrollbar-width: thin;
            padding-bottom: 0.35rem;
        }}
        [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar {{
            height: 6px;
        }}
        [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar-thumb {{
            background: var(--rq-border);
            border-radius: 999px;
        }}
        @media (max-width: 980px) {{
            [data-testid="stAppViewContainer"] > .main .block-container {{
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }}
            [data-testid="stTabs"] button {{
                min-height: 42px;
                padding: 0.5rem 0.8rem;
            }}
            [data-testid="stTabs"] button p {{
                font-size: 0.86rem;
            }}
            .rq-card {{
                padding: 0.9rem 0.92rem;
            }}
            .rq-card-value {{
                font-size: 1.55rem;
            }}
        }}
        {field_css}
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


def responsive_columns(spec: int | list[float], *, field_mode: bool, gap: str = "medium") -> list[Any]:
    if field_mode:
        count = spec if isinstance(spec, int) else len(spec)
        return [st.container() for _ in range(max(1, count))]
    return list(st.columns(spec, gap=gap))


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


def format_table_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    if isinstance(value, str) and value.startswith("<span class='rq-badge"):
        return value
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return str(value.isoformat())
        except TypeError:
            pass
    if isinstance(value, float):
        return f"{value:,.2f}"
    return html.escape(str(value))


def render_data_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No records available.")
        return

    display_df = df.copy()
    for column in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[column]):
            display_df[column] = pd.to_datetime(display_df[column]).dt.strftime("%Y-%m-%d")
        else:
            display_df[column] = display_df[column].map(format_table_value)

    table_html = display_df.to_html(index=False, escape=False, classes="rq-table")
    st.markdown(f"<div class='rq-table-wrap'>{table_html}</div>", unsafe_allow_html=True)


def attention_badge(level: str) -> str:
    normalized = str(level or "Low").lower()
    badge_level = "info"
    if normalized == "watch":
        badge_level = "warning"
    elif normalized == "elevated":
        badge_level = "warning"
    elif normalized == "high":
        badge_level = "critical"
    elif normalized == "low":
        badge_level = "success"
    return highlight_badge(badge_level, str(level or "Low").upper())


def unit_type_badge(label: str) -> str:
    return highlight_badge("info", str(label or "management unit").upper())


def activity_status_badge(label: str) -> str:
    normalized = str(label or "No Activity").lower()
    badge_level = "info"
    if normalized == "active":
        badge_level = "success"
    elif normalized in {"recent", "completed"}:
        badge_level = "warning"
    return highlight_badge(badge_level, str(label or "No Activity").upper())


def planner_urgency_badge(label: str) -> str:
    normalized = str(label or "Watch").lower()
    badge_level = "info"
    if normalized == "low":
        badge_level = "success"
    elif normalized in {"watch", "elevated"}:
        badge_level = "warning"
    elif normalized == "high":
        badge_level = "critical"
    return highlight_badge(badge_level, str(label or "Watch").upper())


def prepare_management_units_table(units_df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "unit_id": "Unit ID",
        "name": "Name",
        "unit_type": "Unit Type",
        "acres": "Acres",
        "assigned_livestock": "Assigned Livestock",
        "current_activity": "Current Activity",
        "current_status": "Activity Status",
        "recent_activity": "Recent Activity",
        "active_head_count": "Active Head",
        "utilization_label": "Load Heuristic",
        "utilization_per_acre_30": "AUD / Acre (30d)",
        "condition_score": "Condition Score",
        "vegetation_status": "Vegetation",
        "drought_category": "Drought",
        "attention_score": "Attention Score",
        "attention_level": "Attention Level",
        "recommendation": "Current Guidance",
    }
    display_df = units_df.rename(columns=rename_map).copy()
    if "Attention Level" in display_df.columns:
        display_df["Attention Level"] = display_df["Attention Level"].map(attention_badge)
    if "Activity Status" in display_df.columns:
        display_df["Activity Status"] = display_df["Activity Status"].map(activity_status_badge)
    if "Load Heuristic" in display_df.columns:
        display_df["Load Heuristic"] = display_df["Load Heuristic"].map(
            lambda value: highlight_badge(
                "success"
                if str(value) in {"Resting", "Light"}
                else "warning"
                if str(value) in {"Moderate", "Elevated"}
                else "critical",
                str(value or "Resting").upper(),
            )
        )
    if "Unit Type" in display_df.columns:
        display_df["Unit Type"] = display_df["Unit Type"].map(unit_type_badge)
    return display_df


def prepare_attention_queue_table(units_df: pd.DataFrame) -> pd.DataFrame:
    display_df = units_df.rename(
        columns={
            "unit_id": "Unit ID",
            "name": "Name",
            "unit_type": "Unit Type",
            "assigned_livestock": "Assigned Livestock",
            "current_activity": "Current Activity",
            "current_status": "Activity Status",
            "recent_activity": "Recent Activity",
            "active_head_count": "Active Head",
            "utilization_label": "Load Heuristic",
            "utilization_per_acre_30": "AUD / Acre (30d)",
            "attention_score": "Attention Score",
            "attention_level": "Attention Level",
            "recommendation": "Guidance",
            "notes": "Notes",
        }
    ).copy()
    if "Attention Level" in display_df.columns:
        display_df["Attention Level"] = display_df["Attention Level"].map(attention_badge)
    if "Activity Status" in display_df.columns:
        display_df["Activity Status"] = display_df["Activity Status"].map(activity_status_badge)
    if "Load Heuristic" in display_df.columns:
        display_df["Load Heuristic"] = display_df["Load Heuristic"].map(
            lambda value: highlight_badge(
                "success"
                if str(value) in {"Resting", "Light"}
                else "warning"
                if str(value) in {"Moderate", "Elevated"}
                else "critical",
                str(value or "Resting").upper(),
            )
        )
    if "Unit Type" in display_df.columns:
        display_df["Unit Type"] = display_df["Unit Type"].map(unit_type_badge)
    return display_df


def prepare_unit_activity_table(activity_df: pd.DataFrame) -> pd.DataFrame:
    display_df = activity_df.rename(
        columns={
            "event_id": "Event ID",
            "unit_id": "Unit ID",
            "unit_name": "Management Unit",
            "activity_type": "Activity Type",
            "livestock_group": "Livestock Group",
            "start_date": "Start",
            "end_date": "End",
            "status": "Status",
            "notes": "Notes",
        }
    ).copy()
    if "Status" in display_df.columns:
        display_df["Status"] = display_df["Status"].map(activity_status_badge)
    return display_df


def prepare_group_load_table(load_df: pd.DataFrame) -> pd.DataFrame:
    return load_df.rename(
        columns={
            "group_id": "Group ID",
            "group_name": "Group Name",
            "species": "Species",
            "current_unit_name": "Current Unit",
            "current_activity": "Current Activity",
            "active_head_count": "Active Head",
            "occupied_units_30": "Units Used (30d)",
            "occupancy_days_30": "Occupancy Days (30d)",
            "animal_unit_days_30": "AUD (30d)",
            "recent_activity": "Recent Activity",
            "recent_window": "Recent Window",
        }
    ).copy()


def prepare_unit_utilization_table(utilization_df: pd.DataFrame) -> pd.DataFrame:
    display_df = utilization_df.rename(
        columns={
            "unit_id": "Unit ID",
            "unit_name": "Management Unit",
            "active_groups": "Active Groups",
            "active_head_count": "Active Head",
            "occupancy_days_30": "Occupancy Days (30d)",
            "animal_unit_days_30": "AUD (30d)",
            "utilization_per_acre_30": "AUD / Acre (30d)",
            "utilization_label": "Load Heuristic",
            "rest_days_since_occupancy": "Rest Days",
        }
    ).copy()
    if "Load Heuristic" in display_df.columns:
        display_df["Load Heuristic"] = display_df["Load Heuristic"].map(
            lambda value: highlight_badge(
                "success"
                if str(value) in {"Resting", "Light"}
                else "warning"
                if str(value) in {"Moderate", "Elevated"}
                else "critical",
                str(value or "Resting").upper(),
            )
        )
    return display_df


def prepare_operation_planner_table(planner_df: pd.DataFrame) -> pd.DataFrame:
    display_df = planner_df.rename(
        columns={
            "unit_id": "Unit ID",
            "unit_name": "Management Unit",
            "unit_type": "Unit Type",
            "suggested_activity_type": "Suggested Activity",
            "suggested_group": "Suggested Group",
            "start_date": "Start",
            "end_date": "End",
            "urgency": "Urgency",
            "rationale": "Why",
        }
    ).copy()
    if "Unit Type" in display_df.columns:
        display_df["Unit Type"] = display_df["Unit Type"].map(unit_type_badge)
    if "Urgency" in display_df.columns:
        display_df["Urgency"] = display_df["Urgency"].map(planner_urgency_badge)
    return display_df


def render_activity_calendar(
    events: dict[str, UnitActivityEvent],
    groups: dict[str, LivestockGroup],
    units: list[ManagementUnit],
    month_start: pd.Timestamp,
    theme: dict[str, object],
) -> None:
    unit_lookup = {unit.unit_id: unit.name for unit in units}
    calendar_start = pd.Timestamp(month_start).normalize().replace(day=1)
    month_end = (calendar_start + pd.offsets.MonthEnd(1)).normalize()
    month_label = calendar_start.strftime("%B %Y")
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(calendar_start.year, calendar_start.month)

    def _event_dates(event: UnitActivityEvent) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        start_value = pd.to_datetime(event.start_date, errors="coerce")
        end_value = pd.to_datetime(event.end_date, errors="coerce") if event.end_date else pd.NaT
        if pd.isna(start_value):
            return None, None
        if pd.isna(end_value):
            end_value = start_value
        return start_value.normalize(), end_value.normalize()

    def _event_chip(event: UnitActivityEvent) -> str:
        group = groups.get(event.livestock_group_id or "")
        group_label = "" if group is None else f" | {group.group_name}"
        unit_label = unit_lookup.get(event.unit_id, event.unit_id)
        return (
            "<div style='margin-top:0.28rem; padding:0.28rem 0.38rem; border-radius:12px; "
            f"background:{theme['info_bg']}; border:1px solid {theme['border']}; font-size:0.72rem; line-height:1.25;'>"
            f"<strong>{html.escape(unit_label)}</strong><br/>{html.escape(event.activity_type.title())}{html.escape(group_label)}"
            "</div>"
        )

    event_lookup: dict[pd.Timestamp, list[UnitActivityEvent]] = {}
    for event in events.values():
        start_value, end_value = _event_dates(event)
        if start_value is None or end_value is None:
            continue
        overlap_start = max(start_value, calendar_start)
        overlap_end = min(end_value, month_end)
        if overlap_end < overlap_start:
            continue
        current_day = overlap_start
        while current_day <= overlap_end:
            event_lookup.setdefault(current_day.normalize(), []).append(event)
            current_day += pd.Timedelta(days=1)

    header_html = "".join(
        f"<th style='padding:0.45rem 0.35rem; text-align:left; font-size:0.73rem; letter-spacing:0.12em; text-transform:uppercase; color:{theme['muted']}; border-bottom:1px solid {theme['border']};'>{day}</th>"
        for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    )
    body_rows: list[str] = []
    for week in weeks:
        cells: list[str] = []
        for day in week:
            day_timestamp = pd.Timestamp(day)
            in_month = day_timestamp.month == calendar_start.month
            day_events = event_lookup.get(day_timestamp.normalize(), [])
            chips = "".join(_event_chip(event) for event in day_events[:3])
            overflow = ""
            if len(day_events) > 3:
                overflow = (
                    f"<div style='margin-top:0.24rem; font-size:0.7rem; color:{theme['muted']};'>"
                    f"+{len(day_events) - 3} more"
                    "</div>"
                )
            cells.append(
                "<td style='vertical-align:top; padding:0.45rem; min-height:132px; height:132px; border:1px solid "
                f"{theme['border']}; background:{theme['card'] if in_month else theme['card_alt']}; width:14.28%;'>"
                f"<div style='font-weight:700; color:{theme['text'] if in_month else theme['muted']};'>{day.day}</div>"
                f"{chips}{overflow}"
                "</td>"
            )
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    calendar_html = (
        "<div class='rq-card' style='padding:1rem 1rem 1.1rem 1rem;'>"
        "<div style='display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; margin-bottom:0.75rem;'>"
        "<div>"
        "<div class='rq-card-title'>Operations Calendar</div>"
        f"<div class='rq-card-subtext'>{month_label} | Logged activities appear on each active day in the month.</div>"
        "</div>"
        f"<div class='rq-inline-note'>Month view is driven entirely by saved activity events for this workspace.</div>"
        "</div>"
        "<div style='overflow:auto;'>"
        "<table style='width:100%; border-collapse:separate; border-spacing:0.2rem;'>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
        "</div>"
    )
    st.markdown(calendar_html, unsafe_allow_html=True)


def build_management_unit_map_frame(
    latest_snapshot: pd.DataFrame,
    management_units: list[ManagementUnit],
) -> pd.DataFrame:
    if latest_snapshot.empty:
        return latest_snapshot.copy()

    units_df = management_units_frame(management_units)
    map_df = latest_snapshot.copy().merge(
        units_df[
            [
                "unit_id",
                "unit_type",
                "assigned_livestock",
                "current_activity",
                "current_status",
                "utilization_label",
                "active_head_count",
                "attention_score",
                "attention_level",
            ]
        ],
        left_on="pasture_id",
        right_on="unit_id",
        how="left",
    )
    color_map = {
        "Low": "GRAZE",
        "Watch": "REST",
        "Elevated": "SUPPLEMENT",
        "High": "DESTOCK WARNING",
    }
    map_df["map_recommendation"] = map_df["attention_level"].map(color_map).fillna(map_df["recommendation"])
    return map_df


def summarize_attention_items(management_units: list[ManagementUnit]) -> list[ManagementUnit]:
    return [unit for unit in management_units if unit.condition is not None][:3]


def image_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix == ".svg":
        mime = "image/svg+xml"
    elif suffix == ".ico":
        mime = "image/x-icon"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_dashboard_header(
    runtime_settings: Settings,
    last_updated: pd.Timestamp,
    total_acres: float,
    pasture_count: int,
    boundary_mode: str,
    map_basemap: str,
    logo_path: Path,
) -> None:
    profile = runtime_settings.ranch_profile
    pasture_label = (
        f"1 {unit_term(profile)}"
        if pasture_count == 1
        else f"{pasture_count} {unit_term(profile, plural=True)}"
    )
    boundary_badge = highlight_badge("info", "DEFAULT BOUNDARY")
    if boundary_mode == "uploaded":
        boundary_badge = highlight_badge("success", "UPLOADED BOUNDARY")
    elif boundary_mode == "saved":
        boundary_badge = highlight_badge("success", "SAVED BOUNDARY")
    basemap_badge = highlight_badge("info", f"{MAP_BASEMAP_LABELS.get(map_basemap, map_basemap).upper()} MAP")
    logo_uri = image_data_uri(logo_path)
    logo_html = (
        f"<div class='rq-brand-mark'><img class='rq-brand-logo' src='{logo_uri}' alt='RangeIQ logo' /></div>"
        if logo_uri
        else ""
    )
    st.markdown(
        (
            "<div class='rq-card rq-brand-banner'>"
            f"{logo_html}"
            "<div class='rq-brand-copy'>"
            f"<div class='rq-hero-kicker'>{html.escape(runtime_settings.pilot_name)}</div>"
            f"<div class='rq-brand-title'>{html.escape(runtime_settings.ranch.name)}</div>"
            f"<div class='rq-brand-meta'>{html.escape(runtime_settings.ranch.address)}</div>"
            f"<div class='rq-brand-meta'>{runtime_settings.ranch.latitude:.4f}, {runtime_settings.ranch.longitude:.4f} | "
            f"{pasture_label} | {total_acres:,.1f} acres</div>"
            f"<div class='rq-brand-meta'>Updated {last_updated.strftime('%Y-%m-%d %H:%M')}</div>"
            f"<div style='margin-top:0.8rem'>{boundary_badge}{basemap_badge}</div>"
            "</div>"
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
    runtime.ranch_profile = RanchProfile(
        ranch_type=str(st.session_state.ranch_type),
        management_style=str(st.session_state.management_style),
        primary_goals=list(st.session_state.primary_goals),
        rotates_animals=bool(st.session_state.rotates_animals),
        preferred_unit_term=str(st.session_state.preferred_unit_term),
        default_unit_type=str(st.session_state.default_unit_type),
        livestock_species=list(st.session_state.livestock_species),
        notes=str(st.session_state.ranch_profile_notes),
    )
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
        if existing.is_file():
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


def build_leaflet_map_html(
    latest_snapshot: pd.DataFrame,
    theme: dict[str, object],
    *,
    basemap: str,
    workspace_id: str,
    selected_unit_id: str,
) -> str:
    recommendation_rgba = theme["recommendation_rgba"]
    polygon_records = []

    for row in latest_snapshot.itertuples(index=False):
        map_recommendation = getattr(row, "map_recommendation", row.recommendation)
        unit_id = str(getattr(row, "unit_id", row.pasture_id))
        is_selected = unit_id == selected_unit_id
        polygon_records.append(
            {
                "name": row.name,
                "unit_id": unit_id,
                "unit_type": getattr(row, "unit_type", "management unit"),
                "assigned_livestock": getattr(row, "assigned_livestock", "none assigned"),
                "current_activity": getattr(row, "current_activity", "No activity logged"),
                "current_status": getattr(row, "current_status", "No Activity"),
                "utilization_label": getattr(row, "utilization_label", "Resting"),
                "active_head_count": int(getattr(row, "active_head_count", 0) or 0),
                "utilization_per_acre_30": float(getattr(row, "utilization_per_acre_30", 0.0) or 0.0),
                "path": [[float(point[1]), float(point[0])] for point in row.geometry],
                "recommendation": row.recommendation,
                "map_recommendation": map_recommendation,
                "condition_score": float(row.pasture_condition_score),
                "grazing_pressure": float(row.grazing_pressure),
                "water_risk_score": float(row.water_risk_score),
                "stocking_risk_score": float(row.stocking_risk_score),
                "attention_score": float(getattr(row, "attention_score", row.stocking_risk_score)),
                "attention_level": str(getattr(row, "attention_level", "Watch")),
                "is_selected": is_selected,
                "selection_url": f"?workspace={workspace_id}&unit={unit_id}",
                "fill_color": _rgba_to_css(recommendation_rgba[map_recommendation], opacity_override=0.22),
                "line_color": _rgba_to_css(recommendation_rgba[map_recommendation], opacity_override=0.95),
            }
        )

    min_lon, min_lat, max_lon, max_lat = _polygon_bounds(latest_snapshot)
    map_bounds = [[min_lat, min_lon], [max_lat, max_lon]]
    polygon_json = json.dumps(polygon_records)
    bounds_json = json.dumps(map_bounds)
    border_color = str(theme["border"])
    card_color = str(theme["card"])
    text_color = str(theme["text"])
    muted_color = str(theme["muted"])
    selected_polygon = next((polygon for polygon in polygon_records if polygon["unit_id"] == selected_unit_id), None)
    selected_summary = {}
    if selected_polygon is not None:
        selected_summary = {
            "name": selected_polygon["name"],
            "unit_type": selected_polygon["unit_type"],
            "assigned_livestock": selected_polygon["assigned_livestock"],
            "current_activity": selected_polygon["current_activity"],
            "current_status": selected_polygon["current_status"],
            "utilization_label": selected_polygon["utilization_label"],
            "active_head_count": selected_polygon["active_head_count"],
            "utilization_per_acre_30": selected_polygon["utilization_per_acre_30"],
            "attention_level": selected_polygon["attention_level"],
            "attention_score": selected_polygon["attention_score"],
            "recommendation": selected_polygon["recommendation"],
        }
    selected_summary_json = json.dumps(selected_summary)
    basemap_config = LEAFLET_BASEMAPS.get(basemap, LEAFLET_BASEMAPS["naip"])
    basemap_config_json = json.dumps(basemap_config)
    use_tile_layer = basemap != "plain"

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
        #rangeiq-map {{
          width: 100%;
          height: 520px;
          border-radius: 20px;
          overflow: hidden;
          border: 1px solid {border_color};
          background: {card_color};
          position: relative;
        }}
        .leaflet-container {{
          font-family: Georgia, "Times New Roman", serif;
          background: {card_color};
        }}
        .leaflet-interactive {{
          cursor: pointer;
        }}
        .rq-map-panel {{
          position: absolute;
          z-index: 1000;
          background: {card_color};
          color: {text_color};
          border: 1px solid {border_color};
          border-radius: 18px;
          box-shadow: 0 18px 45px rgba(38, 28, 18, 0.16);
          padding: 0.9rem 1rem;
          max-width: 270px;
          backdrop-filter: blur(10px);
        }}
        .rq-map-panel h4 {{
          margin: 0 0 0.35rem 0;
          font-size: 1rem;
        }}
        .rq-map-panel p {{
          margin: 0.25rem 0;
          font-size: 0.88rem;
          line-height: 1.35;
        }}
        .rq-map-kicker {{
          font-size: 0.72rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: {muted_color};
          margin-bottom: 0.35rem;
        }}
        .rq-map-chip {{
          display: inline-block;
          border-radius: 999px;
          padding: 0.18rem 0.5rem;
          margin: 0.2rem 0.3rem 0 0;
          border: 1px solid {border_color};
          font-size: 0.73rem;
          font-weight: 700;
          background: rgba(255,255,255,0.5);
        }}
        #rq-selected-unit-panel {{
          top: 12px;
          left: 12px;
        }}
      </style>
    </head>
    <body>
      <div id="rangeiq-map">
        <div id="rq-selected-unit-panel" class="rq-map-panel"></div>
      </div>
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        const polygons = {polygon_json};
        const bounds = {bounds_json};
        const map = L.map('rangeiq-map', {{
          zoomControl: true,
          attributionControl: true,
          scrollWheelZoom: false
        }});
        const selectedPanel = document.getElementById('rq-selected-unit-panel');
        const basemapConfig = {basemap_config_json};
        const useTileLayer = {str(use_tile_layer).lower()};
        const defaultSelected = {selected_summary_json};

        const renderSelectedPanel = (polygon) => {{
          if (!polygon) {{
            selectedPanel.style.display = 'none';
            selectedPanel.innerHTML = '';
            return;
          }}
          selectedPanel.style.display = 'block';
          selectedPanel.innerHTML = `
            <div class="rq-map-kicker">Selected Unit</div>
            <h4>${{polygon.name}}</h4>
            <p><strong>${{polygon.unit_type}}</strong> | Attention ${{polygon.attention_level}} (${{polygon.attention_score.toFixed(1)}})</p>
            <p><strong>Livestock:</strong> ${{polygon.assigned_livestock}}</p>
            <p><strong>Operations:</strong> ${{polygon.current_activity}} (${{polygon.current_status}})</p>
            <p><strong>Load:</strong> ${{polygon.utilization_label}} | AUD/ac ${{polygon.utilization_per_acre_30.toFixed(2)}} | Active head ${{polygon.active_head_count}}</p>
            <p><strong>Guidance:</strong> ${{polygon.recommendation}}</p>
          `;
        }};

        if (useTileLayer) {{
          const tileOptions = {{
            attribution: basemapConfig.attribution,
            maxZoom: basemapConfig.max_zoom || 20,
          }};
          if (basemapConfig.max_native_zoom) {{
            tileOptions.maxNativeZoom = basemapConfig.max_native_zoom;
          }}
          if (basemapConfig.subdomains) {{
            tileOptions.subdomains = basemapConfig.subdomains;
          }}
          L.tileLayer(basemapConfig.url, tileOptions).addTo(map);
        }}
        renderSelectedPanel(defaultSelected && Object.keys(defaultSelected).length ? defaultSelected : null);

        polygons.forEach((polygon) => {{
          const popup = `
            <div style="min-width:190px">
              <div style="font-weight:700; margin-bottom:0.35rem">${{polygon.name}}</div>
              <div>Type: ${{polygon.unit_type}}</div>
              <div>Assigned livestock: ${{polygon.assigned_livestock}}</div>
              <div>Operations: ${{polygon.current_activity}} (${{polygon.current_status}})</div>
              <div>Load heuristic: ${{polygon.utilization_label}} | Active head: ${{polygon.active_head_count}}</div>
              <div>Guidance: ${{polygon.recommendation}}</div>
              <div>Condition score: ${{polygon.condition_score.toFixed(1)}}</div>
              <div>Attention score: ${{polygon.attention_score.toFixed(1)}} (${{polygon.attention_level}})</div>
              <div>Grazing pressure: ${{polygon.grazing_pressure.toFixed(2)}}</div>
              <div>Water risk: ${{polygon.water_risk_score.toFixed(1)}}</div>
              <div>Stocking risk: ${{polygon.stocking_risk_score.toFixed(1)}}</div>
              <div style="margin-top:0.5rem; font-weight:700; color:#234f34;">Click polygon to focus this unit</div>
            </div>
          `;

          const layer = L.polygon(polygon.path, {{
            color: polygon.line_color,
            weight: polygon.is_selected ? 5 : 3,
            fillColor: polygon.fill_color,
            fillOpacity: polygon.is_selected ? 1.0 : 0.82
          }}).addTo(map).bindPopup(popup);
          layer.on('click', () => {{
            renderSelectedPanel(polygon);
            if (polygon.is_selected) {{
              layer.openPopup();
              return;
            }}
            window.top.location.assign(polygon.selection_url);
          }});
        }});

        map.fitBounds(bounds, {{ padding: [18, 18] }});
      </script>
    </body>
    </html>
    """


def render_pasture_map(
    latest_snapshot: pd.DataFrame,
    theme: dict[str, object],
    basemap: str,
    *,
    workspace_id: str,
    selected_unit_id: str,
) -> None:
    try:
        components.html(
            build_leaflet_map_html(
                latest_snapshot,
                theme,
                basemap=basemap,
                workspace_id=workspace_id,
                selected_unit_id=selected_unit_id,
            ),
            height=536,
        )
    except Exception as exc:
        st.warning(f"RangeIQ could not render the interactive ranch map for the current basemap. {exc}")


def render_map_attention_legend(theme: dict[str, object]) -> None:
    recommendation_rgba = theme["recommendation_rgba"]
    border_color = str(theme["border"])
    card_color = str(theme["card"])
    text_color = str(theme["text"])
    muted_color = str(theme["muted"])
    legend_rows = [
        ("GRAZE", "Ready / strong"),
        ("REST", "Recover / watch"),
        ("SUPPLEMENT", "Support / moderate concern"),
        ("REDUCE STOCKING", "Pressure building"),
        ("DESTOCK WARNING", "High attention"),
    ]
    row_html = "".join(
        (
            "<div style='display:flex; align-items:center; gap:0.6rem; margin-top:0.42rem;'>"
            f"<span style=\"width:18px; height:12px; border-radius:999px; display:inline-block; background:{_rgba_to_css(recommendation_rgba[key], opacity_override=0.18)}; border:1px solid {_rgba_to_css(recommendation_rgba[key], opacity_override=0.95)};\"></span>"
            f"<span>{html.escape(label)}</span>"
            "</div>"
        )
        for key, label in legend_rows
    )
    st.markdown(
        (
            f"<div style='border:1px solid {border_color}; border-radius:18px; background:{card_color}; color:{text_color}; "
            "padding:0.9rem 1rem; margin-top:0.35rem;'>"
            f"<div style='font-size:0.72rem; letter-spacing:0.18em; text-transform:uppercase; color:{muted_color}; margin-bottom:0.35rem;'>Map Legend</div>"
            "<div style='font-weight:700; font-size:1rem;'>Attention & Guidance</div>"
            f"{row_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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


def render_station_cards(status_df: pd.DataFrame, *, field_mode: bool = False) -> None:
    if status_df.empty:
        st.info("No station status records are available.")
        return

    columns = responsive_columns(min(3, len(status_df)), field_mode=field_mode, gap="small")
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
apply_display_mode(str(st.session_state.view_mode))
field_mode = str(st.session_state.view_mode) == "Field Mode"
if st.session_state.get("field_shell_section") not in FIELD_SECTION_OPTIONS:
    st.session_state.field_shell_section = FIELD_SECTION_OPTIONS[0]

active_field_section = str(st.session_state.field_shell_section) if field_mode else None

if field_mode:
    st.markdown("<div class='rq-control-kicker'>Field Mode</div>", unsafe_allow_html=True)
    st.markdown("<div class='rq-control-title'>Phone Workspace</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='rq-control-copy'>Use this compact shell for quick ranch checks, map review, and field observations without the full desktop tab layout.</div>",
        unsafe_allow_html=True,
    )
    st.selectbox(
        "Field Navigation",
        options=FIELD_SECTION_OPTIONS,
        key="field_shell_section",
        format_func=lambda value: FIELD_SECTION_SHORT_LABELS.get(value, value),
    )
    st.radio(
        "Appearance",
        options=[LIGHT_THEME["name"], DARK_THEME["name"]],
        key="theme_mode",
        horizontal=True,
        label_visibility="collapsed",
    )
    st.radio(
        "Workspace Layout",
        options=["Desktop Workspace", "Field Mode"],
        key="view_mode",
        horizontal=True,
        label_visibility="collapsed",
    )
    if st.button("Refresh Ranch Intelligence", use_container_width=True):
        st.session_state.data_refresh_nonce += 1
        st.rerun()
    st.caption("Phone mode keeps the map, selected unit, and current operational context close at hand. Data and model outputs stay cached until you refresh.")

if field_mode:
    dashboard_shell = st.container() if active_field_section == "Dashboard" else None
    units_shell = st.container() if active_field_section == "Management Units" else None
    vegetation_shell = st.container() if active_field_section == "Vegetation & Land Health" else None
    livestock_shell = st.container() if active_field_section == "Livestock & Management" else None
    data_shell = st.container() if active_field_section == "Data & Providers" else None
    settings_shell = st.container() if active_field_section == "Settings" else None
    sensors_shell = st.container() if active_field_section == "Sensors" else None
else:
    (
        dashboard_shell,
        units_shell,
        vegetation_shell,
        livestock_shell,
        data_shell,
        settings_shell,
        sensors_shell,
    ) = st.tabs(FIELD_SECTION_OPTIONS)

uploaded_boundary = None
if settings_shell is not None:
    with settings_shell:
            st.subheader("Scenario & Boundary")
            uploaded_boundary = st.file_uploader("Upload ranch or management-unit boundary", type=["geojson", "json", "kml", "kmz"])
            scenario_cols = responsive_columns(3, field_mode=field_mode, gap="medium")
            scenario_cols[0].slider("Weekly modeling window", min_value=12, max_value=104, step=2, key="weeks")
            scenario_cols[1].slider("Vegetation history (years)", min_value=5, max_value=10, key="history_years")
            scenario_cols[2].number_input("Scenario seed", min_value=1, step=1, key="seed")
            st.caption(
                "Upload a GeoJSON, JSON, KML, or KMZ file from Google Earth Pro or another mapping tool to replace the default ranch geometry. "
                "These settings drive the current ranch-intelligence run and can be saved to your account."
            )

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
    workspace_id=CURRENT_WORKSPACE_ID,
    refresh_nonce=int(st.session_state.data_refresh_nonce),
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
        ndvi_dates = pd.to_datetime(vegetation_ndvi_df["date"])
        if getattr(ndvi_dates.dt, "tz", None) is not None:
            ndvi_dates = ndvi_dates.dt.tz_convert("UTC").dt.tz_localize(None)
        vegetation_ndvi_df["month_start"] = ndvi_dates.dt.to_period("M").dt.to_timestamp()
ranch_profile = runtime_settings.ranch_profile
management_unit_overrides = get_management_unit_overrides()
livestock_groups = get_livestock_groups()
unit_activity_events = get_unit_activity_events()
unit_feedback_labels = get_unit_feedback_labels()
management_units = build_management_units(
    latest_snapshot,
    vegetation_summary_df,
    ranch_profile,
    overrides=management_unit_overrides,
    livestock_groups=livestock_groups,
)
activity_summary_lookup = build_unit_activity_summary_lookup(unit_activity_events, livestock_groups, management_units)
management_units = attach_activity_summaries(management_units, activity_summary_lookup)
utilization_summary_lookup = build_unit_utilization_summaries(management_units, livestock_groups, unit_activity_events)
management_units = attach_utilization_summaries(management_units, utilization_summary_lookup)
management_units_df = management_units_frame(management_units)
activity_log_df = unit_activity_frame(unit_activity_events, livestock_groups, management_units)
unit_feedback_df = unit_feedback_frame(unit_feedback_labels, management_units)
feedback_dataset_df = build_feedback_dataset(unit_feedback_labels, management_units, ranch_profile, livestock_groups)
feedback_dataset_summary = summarize_feedback_dataset(feedback_dataset_df)
feedback_calibration_df = build_feedback_calibration_dataset(feedback_dataset_df)
feedback_calibration_summary = summarize_feedback_calibration_dataset(feedback_calibration_df)
feedback_shadow_review_df = build_feedback_shadow_review_dataset(feedback_calibration_df, latest_snapshot)
feedback_shadow_review_summary = summarize_feedback_shadow_review_dataset(feedback_shadow_review_df)
group_load_df = livestock_group_load_frame(build_livestock_group_load_summaries(livestock_groups, unit_activity_events, management_units))
unit_utilization_df = unit_utilization_frame(utilization_summary_lookup, management_units)
planner_suggestions = build_operation_planner_suggestions(management_units, ranch_profile, livestock_groups)
planner_df = operation_planner_frame(planner_suggestions)
map_snapshot = build_management_unit_map_frame(latest_snapshot, management_units)
primary_group = primary_livestock_group(ranch_profile)
weather_bundle = load_weather_bundle_cached(
    runtime_settings=runtime_settings,
    lat=runtime_settings.ranch.latitude,
    lon=runtime_settings.ranch.longitude,
    provider=runtime_settings.weather.provider,
    refresh_bucket=_refresh_bucket(runtime_settings.weather.refresh_minutes),
    refresh_nonce=int(st.session_state.data_refresh_nonce),
)
alert_bundle = load_alert_bundle_cached(
    runtime_settings=runtime_settings,
    lat=runtime_settings.ranch.latitude,
    lon=runtime_settings.ranch.longitude,
    provider=runtime_settings.alerts.provider,
    refresh_bucket=_refresh_bucket(runtime_settings.alerts.refresh_minutes),
    refresh_nonce=int(st.session_state.data_refresh_nonce),
)

fire_assessment = assess_fire_risk(
    current_weather=WeatherService.current_as_dict(weather_bundle),
    alerts_df=alert_bundle.alerts,
    latest_snapshot=latest_snapshot,
    sensor_status_df=pd.DataFrame(),
    sensor_readings_df=pd.DataFrame(),
    app_settings=runtime_settings,
)

selected_unit_default = management_units[0].unit_id if management_units else latest_snapshot["pasture_id"].iloc[0]
available_unit_ids = management_units_df["unit_id"].astype(str).tolist()
selected_unit_id = get_selected_unit_id(available_unit_ids, selected_unit_default)
selected_unit = next((unit for unit in management_units if unit.unit_id == selected_unit_id), management_units[0])
selected_pasture = selected_unit.unit_id
selected_pasture_name = selected_unit.name
selected_activity_summary = activity_summary_lookup.get(selected_unit.unit_id, UnitActivitySummary(unit_id=selected_unit.unit_id))
selected_utilization_summary = utilization_summary_lookup.get(selected_unit.unit_id)
selected_planner_suggestion = next((item for item in planner_suggestions if item.unit_id == selected_unit.unit_id), None)
selected_feedback_df = (
    unit_feedback_df.loc[unit_feedback_df["unit_id"] == selected_unit.unit_id].copy()
    if not unit_feedback_df.empty
    else pd.DataFrame()
)
current_weather = weather_bundle.current
last_updated = max(weather_bundle.loaded_at, alert_bundle.loaded_at, artifacts.public_data_bundle.loaded_at)
total_acres = float(latest_snapshot["acres"].sum()) if "acres" in latest_snapshot.columns else 0.0
pasture_count = int(len(latest_snapshot))
provider_modes = [weather_bundle.mode, alert_bundle.mode] + [status.mode for status in artifacts.public_data_bundle.source_status]
provider_fallback_active = any(mode.endswith("fallback-mock") or mode == "stale-cache" for mode in provider_modes)
action_pastures = management_units_df.loc[
    management_units_df["recommendation"].isin(["SUPPLEMENT", "REDUCE STOCKING", "DESTOCK WARNING"])
].copy()
vegetation_source_status = next(
    (status for status in artifacts.public_data_bundle.source_status if status.component == "Vegetation"),
    None,
)

top_shell_cols = responsive_columns([1.45, 0.78], field_mode=field_mode, gap="medium")
with top_shell_cols[0]:
    logo_path = get_logo_path(st.session_state.theme_mode)
    render_dashboard_header(
        runtime_settings=runtime_settings,
        last_updated=last_updated,
        total_acres=total_acres,
        pasture_count=pasture_count,
        boundary_mode=boundary_mode,
        map_basemap=st.session_state.map_basemap,
        logo_path=logo_path,
    )
with top_shell_cols[1]:
    if field_mode:
        render_signal_card(
            title="Field Focus",
            value=FIELD_SECTION_SHORT_LABELS.get(str(active_field_section or "Dashboard"), "Map & Alerts"),
            subtitle="Use the Field Navigation control above to jump between the map, units, land health, and settings on a phone.",
            badges=[highlight_badge("info", "FIELD MODE")],
        )
    else:
        st.markdown("<div class='rq-control-kicker'>Display</div>", unsafe_allow_html=True)
        st.markdown("<div class='rq-control-title'>Appearance</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='rq-control-copy'>Switch between a warm daylight field view and a darker low-glare operations mode.</div>",
            unsafe_allow_html=True,
        )
        st.segmented_control(
            "Color Mode",
            options=["High Plains Day", "Mesquite Night"],
            key="theme_mode",
            label_visibility="collapsed",
            width="stretch",
        )
        st.radio(
            "Workspace Layout",
            options=["Desktop Workspace", "Field Mode"],
            key="view_mode",
            horizontal=True,
            label_visibility="collapsed",
        )
        if st.button("Refresh Ranch Intelligence", use_container_width=True):
            st.session_state.data_refresh_nonce += 1
            st.rerun()
        st.caption("Map, providers, and model outputs stay cached until you refresh or change scenario inputs.")

    if dashboard_shell is not None:
        with dashboard_shell:
            if boundary_mode == "default":
                st.info("The default ranch boundary is the single Caja Caliente management unit drawn from your provided Alpine property corners.")
            elif boundary_mode == "saved":
                st.info("RangeIQ loaded your last saved ranch boundary automatically. Upload a new file or save again if you want to replace it.")

            if provider_fallback_active:
                st.warning("One or more public-data providers failed in this run. RangeIQ automatically fell back to mock data to keep the dashboard operational.")

            selected_condition = selected_unit.condition
            high_attention_count = int((management_units_df["attention_level"] == "High").sum()) if not management_units_df.empty else 0
            mean_condition = float(pd.to_numeric(management_units_df["condition_score"], errors="coerce").fillna(0).mean()) if not management_units_df.empty else 0.0
            top_metrics = responsive_columns(4, field_mode=field_mode, gap="small")
            top_metrics[0].metric("Current Temp", format_number(current_weather.temperature_f, " F", 1), f"Feels like {format_number(current_weather.feels_like_f, ' F', 1)}")
            top_metrics[1].metric(unit_term(ranch_profile, plural=True, title=True), f"{pasture_count}", f"{total_acres:,.1f} acres")
            top_metrics[2].metric("Attention Queue", f"{high_attention_count}", f"Avg condition {mean_condition:.1f}")
            top_metrics[3].metric("Fire Risk", f"{fire_assessment.category}", f"Score {fire_assessment.score:.1f}")

            map_col, summary_col = responsive_columns([1.26, 0.84], field_mode=field_mode, gap="medium")
            with map_col:
                st.subheader("Ranch Intelligence Map")
                render_pasture_map(
                    map_snapshot,
                    theme,
                    st.session_state.map_basemap,
                    workspace_id=CURRENT_WORKSPACE_ID,
                    selected_unit_id=selected_unit_id,
                )
                st.caption(
                    "This map centers the ranch boundary and uploaded management-unit polygons first. "
                    "RangeIQ shades each area by current attention level, but the only on-map detail panel appears when a management unit is selected. "
                    "Use the legend below the map and the quick-focus buttons for extra context without crowding the map view."
                )
                render_map_attention_legend(theme)
                focus_candidates = management_units_df.sort_values(["attention_score", "condition_score"], ascending=[False, True]).head(6)
                st.markdown("**Quick Focus Units**")
                focus_cols = responsive_columns(max(1, min(3, len(focus_candidates))), field_mode=field_mode, gap="small")
                for idx, row in enumerate(focus_candidates.itertuples(index=False)):
                    with focus_cols[idx % len(focus_cols)]:
                        label = f"{row.name} ({row.attention_level})"
                        if st.button(label, key=f"focus-unit-{row.unit_id}", use_container_width=True):
                            st.session_state.selected_unit_id = row.unit_id
                            st.query_params["unit"] = row.unit_id
                            st.rerun()

            with summary_col:
                st.subheader(f"Selected {unit_term(ranch_profile, title=True)}")
                st.caption(f"{selected_unit.name} | {selected_unit.unit_type} | {selected_unit.acres:,.1f} acres")
                if selected_condition is not None:
                    render_signal_card(
                        title="Attention Level",
                        value=f"{selected_condition.attention_level} ({selected_condition.attention_score:.1f})",
                        subtitle=selected_condition.recommendation_summary,
                        badges=[attention_badge(selected_condition.attention_level), unit_type_badge(selected_unit.unit_type)],
                    )
                    activity_subtitle = selected_activity_summary.current_window or selected_activity_summary.recent_window or "No use/rest history has been logged yet."
                    if selected_activity_summary.current_group_label:
                        activity_subtitle = f"{selected_activity_summary.current_group_label} | {activity_subtitle}"
                    render_signal_card(
                        title="Operations Snapshot",
                        value=selected_activity_summary.current_activity,
                        subtitle=activity_subtitle,
                        badges=[activity_status_badge(selected_activity_summary.status_label)],
                    )
                    if selected_utilization_summary is not None:
                        utilization_subtitle = (
                            f"{format_number(selected_utilization_summary.utilization_per_acre_30, '', 2)} AUD/ac over 30d | "
                            f"Active head {selected_utilization_summary.active_head_count}"
                        )
                        if selected_utilization_summary.rest_days_since_occupancy is not None:
                            utilization_subtitle += f" | Rest {selected_utilization_summary.rest_days_since_occupancy}d"
                        render_signal_card(
                            title="Utilization Heuristic",
                            value=selected_utilization_summary.utilization_label,
                            subtitle=utilization_subtitle,
                            badges=[highlight_badge(
                                "success"
                                if selected_utilization_summary.utilization_label in {"Resting", "Light"}
                                else "warning"
                                if selected_utilization_summary.utilization_label in {"Moderate", "Elevated"}
                                else "critical",
                                selected_utilization_summary.utilization_label.upper(),
                            )],
                        )
                    if selected_planner_suggestion is not None:
                        planner_window = selected_planner_suggestion.start_date
                        if selected_planner_suggestion.end_date and selected_planner_suggestion.end_date != selected_planner_suggestion.start_date:
                            planner_window = f"{selected_planner_suggestion.start_date} to {selected_planner_suggestion.end_date}"
                        planner_subtitle = selected_planner_suggestion.rationale
                        if selected_planner_suggestion.suggested_group_label:
                            planner_subtitle = (
                                f"{selected_planner_suggestion.suggested_group_label} | {planner_window} | "
                                f"{selected_planner_suggestion.rationale}"
                            )
                        render_signal_card(
                            title="Suggested Next Step",
                            value=str(selected_planner_suggestion.suggested_activity_type).title(),
                            subtitle=planner_subtitle,
                            badges=[planner_urgency_badge(selected_planner_suggestion.urgency)],
                        )
                        if st.button(
                            f"Schedule Suggested Activity for {selected_unit.name}",
                            key=f"schedule-suggestion-{selected_unit.unit_id}",
                            use_container_width=True,
                        ):
                            if save_planner_suggestion_event(selected_planner_suggestion):
                                st.success("Suggested activity scheduled into the unit timeline. Save Current Setup in Settings if you want it persisted.")
                            else:
                                st.info("That suggested activity is already on the calendar for this unit.")
                            st.rerun()
                    if not selected_feedback_df.empty:
                        latest_feedback = selected_feedback_df.iloc[0]
                        render_signal_card(
                            title="Latest Field Feedback",
                            value=f"{str(latest_feedback['label_value']).title()}",
                            subtitle=(
                                f"{latest_feedback['label_type'].title()} | "
                                f"{latest_feedback['confidence']} confidence | "
                                f"{latest_feedback['observed_on'] or 'undated'}"
                            ),
                            badges=[highlight_badge("info", "FIELD LABEL")],
                        )
                    detail_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                    detail_cols[0].metric("Condition Score", format_number(selected_condition.forage_condition_score, "", 1))
                    detail_cols[1].metric("Vegetation", selected_condition.vegetation_status)
                    detail_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                    detail_cols[0].metric("Drought", selected_condition.drought_category)
                    detail_cols[1].metric("Water Risk", format_number(selected_condition.water_risk_score, "", 1))
                    st.caption(
                        f"Assigned livestock: {', '.join(selected_unit.assigned_livestock) if selected_unit.assigned_livestock else 'none assigned'}"
                    )
                    if selected_activity_summary.recent_activity != "No activity logged":
                        st.caption(
                            f"Recent activity: {selected_activity_summary.recent_activity} | "
                            f"{selected_activity_summary.recent_group_label or 'no group assigned'} | "
                            f"{selected_activity_summary.recent_window}"
                        )

            summary_cards = responsive_columns(3, field_mode=field_mode, gap="medium")
            with summary_cards[0]:
                render_signal_card(
                    title="Ranch Profile",
                    value=ranch_profile.management_style.title(),
                    subtitle=f"{ranch_profile.ranch_type.title()} | {unit_term(ranch_profile, plural=True)}",
                    badges=[highlight_badge("info", "PROFILE")],
                )
            with summary_cards[1]:
                focus_goals = ", ".join(ranch_profile.primary_goals[:2]) if ranch_profile.primary_goals else "general land monitoring"
                render_signal_card(
                    title="Primary Goals",
                    value=focus_goals.title(),
                    subtitle="The dashboard language and recommendations adapt around these goals.",
                    badges=[highlight_badge("success", "GOALS")],
                )
            with summary_cards[2]:
                render_signal_card(
                    title="Livestock Focus",
                    value="No livestock assigned" if primary_group is None else primary_group.species.title(),
                    subtitle="Rotational grazing is now optional; land monitoring and mixed-use setups are supported too.",
                    badges=[highlight_badge("info", "OPERATIONS")],
                )

            st.subheader("Operations Planner Queue")
            st.caption(
                "These suggested next steps are transparent heuristics based on ranch style, current condition, recent activity, and the 30-day utilization signal."
            )
            if planner_df.empty:
                st.info("No planner suggestions are available yet.")
            else:
                render_data_table(prepare_operation_planner_table(planner_df.head(8)))

            weather_col, forecast_col = responsive_columns([0.95, 1.05], field_mode=field_mode, gap="medium")
            with weather_col:
                st.subheader("Current Weather")
                st.caption(f"{current_weather.weather_label} | Source: {current_weather.source}")
                weather_metrics_a = responsive_columns(2, field_mode=field_mode, gap="small")
                weather_metrics_b = responsive_columns(2, field_mode=field_mode, gap="small")
                weather_metrics_c = responsive_columns(2, field_mode=field_mode, gap="small")
                weather_metrics_a[0].metric("Temperature", format_number(current_weather.temperature_f, " F", 1))
                weather_metrics_a[1].metric("Feels Like", format_number(current_weather.feels_like_f, " F", 1))
                weather_metrics_b[0].metric("Humidity", format_number(current_weather.humidity_pct, "%", 0))
                weather_metrics_b[1].metric("Precip Chance", format_number(current_weather.precip_probability_pct, "%", 0))
                weather_metrics_c[0].metric("Wind Dir", current_weather.wind_direction or "--")
                weather_metrics_c[1].metric("Rain Today", format_number(current_weather.rainfall_expected_today_in, " in", 2))
            with forecast_col:
                st.subheader("7-Day Forecast")
                render_data_table(prepare_forecast_table(weather_bundle.forecast))

            risk_col, alert_col = responsive_columns([0.92, 1.08], field_mode=field_mode, gap="medium")
            with risk_col:
                st.plotly_chart(plot_fire_risk_gauge(fire_assessment.score, fire_assessment.category, fire_assessment.color, theme), width="stretch")
                render_fire_risk_panel(fire_assessment)
            with alert_col:
                render_alert_panel(alert_bundle.alerts)

            st.subheader("Priority Attention Items")
            if action_pastures.empty:
                st.success(f"No {unit_term(ranch_profile, plural=True)} currently require elevated follow-up in this scenario.")
            else:
                render_data_table(
                    prepare_management_units_table(
                        action_pastures[
                            [
                                "unit_id",
                                "name",
                                "unit_type",
                                "assigned_livestock",
                                "current_activity",
                                "current_status",
                                "utilization_label",
                                "utilization_per_acre_30",
                                "condition_score",
                                "vegetation_status",
                                "drought_category",
                                "attention_score",
                                "attention_level",
                                "recommendation",
                            ]
                        ]
                    )
                )

            st.subheader("Ranch-Wide Attention Queue")
            attention_queue_df = management_units_df.sort_values(["attention_score", "condition_score"], ascending=[False, True]).head(8)
            render_data_table(
                prepare_attention_queue_table(
                    attention_queue_df[
                        [
                            "unit_id",
                            "name",
                            "unit_type",
                            "assigned_livestock",
                            "current_activity",
                            "current_status",
                            "recent_activity",
                            "active_head_count",
                            "utilization_label",
                            "utilization_per_acre_30",
                            "attention_score",
                            "attention_level",
                            "recommendation",
                            "notes",
                        ]
                    ]
                )
            )

    if sensors_shell is not None:
        with sensors_shell:
            render_under_development_notice(
                "Sensors",
                "We paused live station monitoring while we optimize dashboard performance and finish the next sensor architecture pass.",
            )
            render_under_development_notice(
                "Sensor Network",
                "Meshtastic and remote-station ingestion are still in progress, so the hosted app is not loading that stack right now.",
            )
    if units_shell is not None:
        with units_shell:
            unit_options = management_units_df["unit_id"].tolist()
            selected_option = st.selectbox(
                f"Select {unit_term(ranch_profile, title=True)}",
                options=unit_options,
                index=unit_options.index(st.session_state.selected_unit_id),
                format_func=lambda value: f"{value} - {management_units_df.loc[management_units_df['unit_id'] == value, 'name'].iloc[0]}",
            )
            if selected_option != st.session_state.selected_unit_id:
                st.session_state.selected_unit_id = selected_option
                st.query_params["unit"] = selected_option
                st.rerun()

            current_unit = next((unit for unit in management_units if unit.unit_id == st.session_state.selected_unit_id), selected_unit)
            current_condition = current_unit.condition
            current_unit_utilization = utilization_summary_lookup.get(current_unit.unit_id)
            current_unit_feedback_df = (
                unit_feedback_df.loc[unit_feedback_df["unit_id"] == current_unit.unit_id].copy()
                if not unit_feedback_df.empty
                else pd.DataFrame()
            )
            units_metric_cols = responsive_columns(5, field_mode=field_mode, gap="small")
            units_metric_cols[0].metric("Condition Score", format_number(current_condition.forage_condition_score, "", 1))
            units_metric_cols[1].metric("Attention", f"{current_condition.attention_level}", f"{current_condition.attention_score:.1f}")
            units_metric_cols[2].metric("Vegetation", current_condition.vegetation_status)
            units_metric_cols[3].metric("Drought", current_condition.drought_category)
            units_metric_cols[4].metric("Guidance", current_condition.recommendation_code)
            st.caption(current_condition.recommendation_summary)
            current_unit_activity = activity_summary_lookup.get(current_unit.unit_id, UnitActivitySummary(unit_id=current_unit.unit_id))
            st.caption(
                f"Operations status: {current_unit_activity.status_label} | "
                f"{current_unit_activity.current_activity} | "
                f"{current_unit_activity.current_group_label or 'no group assigned'} | "
                f"{current_unit_activity.current_window or current_unit_activity.recent_window or 'no timeline logged'}"
            )
            if current_unit_utilization is not None:
                st.caption(
                    f"Utilization heuristic: {current_unit_utilization.utilization_label} | "
                    f"30d AUD/ac {format_number(current_unit_utilization.utilization_per_acre_30, '', 2)} | "
                    f"Active head {current_unit_utilization.active_head_count} | "
                    f"Rest days {current_unit_utilization.rest_days_since_occupancy if current_unit_utilization.rest_days_since_occupancy is not None else '--'}"
                )

            source_unit_row = latest_snapshot.loc[latest_snapshot["pasture_id"] == current_unit.unit_id].iloc[0]
            existing_override = management_unit_overrides.get(current_unit.unit_id)
            default_display_name = existing_override.display_name if existing_override and existing_override.display_name else str(source_unit_row["name"])
            default_unit_type = existing_override.unit_type if existing_override else current_unit.unit_type
            default_assigned_group_ids = existing_override.assigned_group_ids if existing_override else list(current_unit.assigned_group_ids)
            default_assigned_livestock = (
                existing_override.assigned_livestock
                if existing_override and existing_override.assigned_livestock
                else list(current_unit.assigned_livestock)
            )
            default_assigned_livestock = [
                value for value in default_assigned_livestock if value in LIVESTOCK_SPECIES_OPTIONS
            ]
            default_notes = existing_override.notes if existing_override is not None else str(source_unit_row.get("notes") or "")

            st.subheader("Edit Management Unit Metadata")
            st.caption(
                "Use unit metadata to adapt the same uploaded boundary file for horse turnouts, hay fields, browse zones, exclusion areas, leased land, or other management uses."
            )
            with st.form(f"unit_metadata_form_{current_unit.unit_id}"):
                metadata_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                unit_display_name = metadata_cols[0].text_input("Display Name", value=default_display_name)
                unit_type_value = metadata_cols[1].selectbox(
                    "Unit Type",
                    options=MANAGEMENT_UNIT_TYPE_OPTIONS,
                    index=MANAGEMENT_UNIT_TYPE_OPTIONS.index(default_unit_type)
                    if default_unit_type in MANAGEMENT_UNIT_TYPE_OPTIONS
                    else 0,
                )
                available_group_ids = list(livestock_groups.keys())
                assigned_group_ids_value = st.multiselect(
                    "Assigned Livestock Groups",
                    options=available_group_ids,
                    default=[group_id for group_id in default_assigned_group_ids if group_id in available_group_ids],
                    format_func=lambda group_id: (
                        f"{livestock_groups[group_id].group_name} ({livestock_groups[group_id].species})"
                        if group_id in livestock_groups
                        else group_id
                    ),
                    help="These named groups are shown in the map, unit summaries, and attention queue.",
                )
                assigned_livestock_value = st.multiselect(
                    "Fallback Assigned Species",
                    options=LIVESTOCK_SPECIES_OPTIONS,
                    default=default_assigned_livestock,
                    help="Used when no named livestock groups are assigned to this management unit.",
                )
                unit_notes_value = st.text_area("Unit Notes", value=default_notes, height=110)
                form_cols = responsive_columns([1, 1, 2], field_mode=field_mode, gap="small")
                save_metadata = form_cols[0].form_submit_button("Apply Unit Metadata")
                clear_metadata = form_cols[1].form_submit_button("Clear Override")

            if save_metadata:
                updated_overrides = get_management_unit_overrides()
                updated_overrides[current_unit.unit_id] = ManagementUnitOverride(
                    unit_id=current_unit.unit_id,
                    display_name=unit_display_name.strip(),
                    unit_type=unit_type_value,
                    assigned_group_ids=list(assigned_group_ids_value),
                    assigned_livestock=list(assigned_livestock_value),
                    notes=unit_notes_value.strip(),
                )
                st.session_state["management_unit_overrides"] = serialize_management_unit_overrides(updated_overrides)
                st.success(f"Updated metadata for {current_unit.name}. Save Current Setup in Settings if you want this persisted for future sessions.")
                st.rerun()
            if clear_metadata:
                updated_overrides = get_management_unit_overrides()
                updated_overrides.pop(current_unit.unit_id, None)
                st.session_state["management_unit_overrides"] = serialize_management_unit_overrides(updated_overrides)
                st.info(f"Cleared custom metadata for {current_unit.name}.")
                st.rerun()

            st.subheader("Field Feedback Labels")
            st.caption(
                "Use quick field labels to record what you actually observed on this unit. These labels are saved with the workspace and are intended to support future model calibration with real ranch feedback."
            )
            if current_unit_feedback_df.empty:
                st.info(f"No field feedback has been logged for {current_unit.name} yet.")
            else:
                render_data_table(
                    current_unit_feedback_df[["observed_on", "label_type", "label_value", "confidence", "notes"]].rename(
                        columns={
                            "observed_on": "Observed On",
                            "label_type": "Label Type",
                            "label_value": "Observed Value",
                            "confidence": "Confidence",
                            "notes": "Notes",
                        }
                    )
                )

            feedback_choices = ["Create New Label"] + (
                current_unit_feedback_df["label_id"].astype(str).tolist() if not current_unit_feedback_df.empty else []
            )
            selected_feedback_key = st.selectbox(
                "Field feedback editor",
                options=feedback_choices,
                format_func=lambda value: (
                    "Create New Label"
                    if value == "Create New Label"
                    else (
                        f"{current_unit_feedback_df.loc[current_unit_feedback_df['label_id'] == value, 'label_type'].iloc[0].title()} | "
                        f"{current_unit_feedback_df.loc[current_unit_feedback_df['label_id'] == value, 'label_value'].iloc[0].title()}"
                    )
                ),
            )
            editing_feedback = unit_feedback_labels.get(selected_feedback_key) if selected_feedback_key != "Create New Label" else None
            feedback_type_default = (
                editing_feedback.label_type if editing_feedback is not None else FEEDBACK_LABEL_TYPE_OPTIONS[0]
            )
            feedback_value_choices = FEEDBACK_VALUE_OPTIONS.get(feedback_type_default, FEEDBACK_VALUE_OPTIONS[FEEDBACK_LABEL_TYPE_OPTIONS[0]])
            feedback_observed_default = (
                pd.to_datetime(editing_feedback.observed_on).date()
                if editing_feedback is not None and editing_feedback.observed_on
                else pd.Timestamp.utcnow().date()
            )
            with st.form(f"unit_feedback_form_{current_unit.unit_id}"):
                feedback_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                feedback_type_value = feedback_cols[0].selectbox(
                    "Field Label Type",
                    options=FEEDBACK_LABEL_TYPE_OPTIONS,
                    index=FEEDBACK_LABEL_TYPE_OPTIONS.index(feedback_type_default) if feedback_type_default in FEEDBACK_LABEL_TYPE_OPTIONS else 0,
                )
                feedback_value_options = FEEDBACK_VALUE_OPTIONS.get(feedback_type_value, feedback_value_choices)
                feedback_value_default = (
                    editing_feedback.label_value
                    if editing_feedback is not None and editing_feedback.label_value in feedback_value_options
                    else feedback_value_options[0]
                )
                feedback_value_value = feedback_cols[1].selectbox(
                    "Observed Value",
                    options=feedback_value_options,
                    index=feedback_value_options.index(feedback_value_default),
                )
                feedback_confidence_value = feedback_cols[2].selectbox(
                    "Confidence",
                    options=FEEDBACK_CONFIDENCE_OPTIONS,
                    index=FEEDBACK_CONFIDENCE_OPTIONS.index(editing_feedback.confidence)
                    if editing_feedback is not None and editing_feedback.confidence in FEEDBACK_CONFIDENCE_OPTIONS
                    else FEEDBACK_CONFIDENCE_OPTIONS.index("medium"),
                )
                feedback_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                feedback_observed_on = feedback_cols[0].date_input("Observed On", value=feedback_observed_default)
                feedback_notes_value = feedback_cols[1].text_area(
                    "Feedback Notes",
                    value="" if editing_feedback is None else editing_feedback.notes,
                    height=110,
                    placeholder="Short field observation, animal behavior note, bare-ground context, water issue, or restoration note...",
                )
                feedback_form_cols = responsive_columns([1, 1, 2], field_mode=field_mode, gap="small")
                save_feedback = feedback_form_cols[0].form_submit_button("Save Label")
                delete_feedback = feedback_form_cols[1].form_submit_button("Delete Label")

            if save_feedback:
                updated_feedback = get_unit_feedback_labels()
                label_id = editing_feedback.label_id if editing_feedback is not None else f"feedback-{uuid4().hex[:10]}"
                updated_feedback[label_id] = UnitFeedbackLabel(
                    label_id=label_id,
                    unit_id=current_unit.unit_id,
                    label_type=feedback_type_value,
                    label_value=feedback_value_value,
                    observed_on=feedback_observed_on.isoformat(),
                    confidence=feedback_confidence_value,
                    notes=feedback_notes_value.strip(),
                )
                st.session_state["unit_feedback_labels"] = serialize_unit_feedback_labels(updated_feedback)
                st.success("Field feedback saved. Save Current Setup in Settings if you want this persisted for future sessions.")
                st.rerun()
            if delete_feedback and editing_feedback is not None:
                updated_feedback = get_unit_feedback_labels()
                updated_feedback.pop(editing_feedback.label_id, None)
                st.session_state["unit_feedback_labels"] = serialize_unit_feedback_labels(updated_feedback)
                st.info("Field feedback label deleted.")
                st.rerun()

            render_data_table(
                prepare_management_units_table(
                    management_units_df[
                        [
                            "unit_id",
                            "name",
                            "unit_type",
                            "acres",
                            "assigned_livestock",
                            "current_activity",
                            "current_status",
                            "recent_activity",
                            "active_head_count",
                            "utilization_label",
                            "utilization_per_acre_30",
                            "condition_score",
                            "vegetation_status",
                            "drought_category",
                            "attention_score",
                            "attention_level",
                            "recommendation",
                        ]
                    ]
                )
            )

            unit_chart_a, unit_chart_b = responsive_columns(2, field_mode=field_mode, gap="medium")
            with unit_chart_a:
                st.plotly_chart(
                    apply_chart_theme(plot_condition_scores(latest_snapshot, theme["recommendation_colors"]), theme),
                    width="stretch",
                )
            with unit_chart_b:
                st.plotly_chart(
                    apply_chart_theme(plot_water_vs_stocking_risk(latest_snapshot, theme["recommendation_colors"]), theme),
                    width="stretch",
                )

    if vegetation_shell is not None:
        with vegetation_shell:
            vegetation_options = management_units_df["unit_id"].tolist()
            vegetation_selected = st.selectbox(
                f"{unit_term(ranch_profile, title=True)} for land-health detail",
                options=vegetation_options,
                index=vegetation_options.index(st.session_state.selected_unit_id),
                format_func=lambda value: f"{value} - {management_units_df.loc[management_units_df['unit_id'] == value, 'name'].iloc[0]}",
            )
            if vegetation_selected != st.session_state.selected_unit_id:
                st.session_state.selected_unit_id = vegetation_selected
                st.query_params["unit"] = vegetation_selected
                st.rerun()

            selected_pasture = st.session_state.selected_unit_id
            selected_vegetation = (
                vegetation_summary_df.loc[vegetation_summary_df["pasture_id"] == selected_pasture].iloc[0]
                if not vegetation_summary_df.empty and selected_pasture in set(vegetation_summary_df["pasture_id"])
                else None
            )
            st.subheader("Vegetation History / Land Health")
            if selected_vegetation is not None:
                ndvi_anomaly_percent_value = pd.to_numeric(selected_vegetation.get("ndvi_anomaly_percent"), errors="coerce")
                ndvi_badge_level = "info" if pd.isna(ndvi_anomaly_percent_value) else ("success" if float(ndvi_anomaly_percent_value) >= 0 else "warning")
                st.caption(
                    f"NDVI source: {selected_vegetation.get('ndvi_source_label', 'Earth Search STAC / Sentinel-2')} | "
                    "RAP source: Rangeland Analysis Platform"
                )
                vegetation_card_cols = responsive_columns(4, field_mode=field_mode, gap="medium")
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
                        title="RangeIQ Land Score",
                        value=f"{format_number(selected_vegetation['rangeiq_vegetation_score'], '', 0)} {str(selected_vegetation['rangeiq_vegetation_category']).upper()}",
                        subtitle=str(selected_vegetation["rangeiq_vegetation_explanation"]),
                        badges=[highlight_badge("success" if str(selected_vegetation["rangeiq_vegetation_category"]) in {"Excellent", "Good"} else "warning" if str(selected_vegetation["rangeiq_vegetation_category"]) in {"Watch", "Stressed"} else "critical", str(selected_vegetation["rangeiq_vegetation_category"]).upper())],
                    )

                if str(selected_vegetation.get("rangeiq_vegetation_drivers", "")).strip():
                    st.caption(f"Main drivers: {selected_vegetation['rangeiq_vegetation_drivers']}")
                if str(selected_vegetation.get("vegetation_warnings", "")).strip():
                    st.warning(selected_vegetation["vegetation_warnings"])
            else:
                st.info(f"Vegetation history is not available for the selected {unit_term(ranch_profile)} in this run.")

            vegetation_chart_a, vegetation_chart_b = responsive_columns(2, field_mode=field_mode, gap="medium")
            with vegetation_chart_a:
                if not vegetation_ndvi_df.empty:
                    st.plotly_chart(apply_chart_theme(plot_public_ndvi_history(vegetation_ndvi_df, selected_pasture), theme), width="stretch")
                else:
                    st.info(f"NDVI history is unavailable for this {unit_term(ranch_profile)}.")
            with vegetation_chart_b:
                if not vegetation_cover_df.empty:
                    st.plotly_chart(apply_chart_theme(plot_rap_cover_history(vegetation_cover_df, selected_pasture), theme), width="stretch")
                else:
                    st.info("RAP cover history is unavailable for this area.")

            vegetation_chart_c, vegetation_chart_d = responsive_columns(2, field_mode=field_mode, gap="medium")
            with vegetation_chart_c:
                if not vegetation_production_df.empty:
                    st.plotly_chart(apply_chart_theme(plot_rap_production_history(vegetation_production_df, selected_pasture), theme), width="stretch")
                else:
                    st.info("RAP production history is unavailable for this area.")
            with vegetation_chart_d:
                st.plotly_chart(apply_chart_theme(plot_rainfall_deficit_history(history_df, selected_pasture), theme), width="stretch")

            vegetation_chart_e, vegetation_chart_f = responsive_columns(2, field_mode=field_mode, gap="medium")
            with vegetation_chart_e:
                st.plotly_chart(apply_chart_theme(plot_ndvi_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")
            with vegetation_chart_f:
                st.plotly_chart(apply_chart_theme(plot_forage_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")

            vegetation_chart_g, vegetation_chart_h = responsive_columns(2, field_mode=field_mode, gap="medium")
            with vegetation_chart_g:
                st.plotly_chart(apply_chart_theme(plot_rainfall_trend(artifacts.scored_data, selected_pasture), theme), width="stretch")
            with vegetation_chart_h:
                st.plotly_chart(
                    apply_chart_theme(plot_recommendation_mix(latest_snapshot, theme["recommendation_colors"]), theme),
                    width="stretch",
                )

    if livestock_shell is not None:
        with livestock_shell:
            ranch_profile_cols = responsive_columns(3, field_mode=field_mode, gap="medium")
            with ranch_profile_cols[0]:
                render_signal_card(
                    title="Management Style",
                    value=ranch_profile.management_style.title(),
                    subtitle=ranch_profile.ranch_type.title(),
                    badges=[highlight_badge("info", "STYLE")],
                )
            with ranch_profile_cols[1]:
                render_signal_card(
                    title="Livestock",
                    value="No livestock" if primary_group is None else primary_group.species.title(),
                    subtitle=f"Rotates animals: {'Yes' if ranch_profile.rotates_animals else 'No'}",
                    badges=[highlight_badge("success", "PROFILE")],
                )
            with ranch_profile_cols[2]:
                goals_value = ", ".join(ranch_profile.primary_goals[:2]).title() if ranch_profile.primary_goals else "General Land Monitoring"
                render_signal_card(
                    title="Primary Goals",
                    value=goals_value,
                    subtitle=f"Preferred terminology: {unit_term(ranch_profile)}",
                    badges=[highlight_badge("info", "GOALS")],
                )
            if ranch_profile.notes.strip():
                st.caption(ranch_profile.notes)

            st.subheader("Operations Summary")
            st.markdown(
                f"RangeIQ is now treating **{unit_term(ranch_profile, plural=True)}** as the core management object for this workspace. "
                f"Recommendations adapt around **{ranch_profile.management_style}**, the assigned livestock profile, and the goals you save in Settings."
            )

            st.subheader("Livestock Groups")
            groups_df = livestock_groups_frame(livestock_groups, management_units)
            if groups_df.empty:
                st.info("No named livestock groups are saved yet. Add groups here if you want cattle classes, horse strings, goat bands, or sheep mobs tied to specific management units.")
            else:
                render_data_table(
                    groups_df.rename(
                        columns={
                            "group_id": "Group ID",
                            "group_name": "Group Name",
                            "species": "Species",
                            "animal_count": "Head",
                            "class_type": "Class / Type",
                            "average_weight": "Avg Weight",
                            "assigned_unit": "Assigned Unit",
                            "notes": "Notes",
                        }
                    )
                )

            st.subheader("Group Occupancy / Load Summary")
            st.caption(
                "This 30-day summary is a transparent operational heuristic based on your logged activity windows, animal counts, and simple animal-unit assumptions."
            )
            if group_load_df.empty:
                st.info("No livestock-group occupancy summary is available yet because no groups or use events have been logged.")
            else:
                render_data_table(prepare_group_load_table(group_load_df))

            group_choices = ["Create New Group"] + sorted(livestock_groups.keys())
            selected_group_key = st.selectbox(
                "Livestock group editor",
                options=group_choices,
                format_func=lambda value: (
                    "Create New Group"
                    if value == "Create New Group"
                    else f"{livestock_groups[value].group_name} ({livestock_groups[value].species})"
                ),
            )
            editing_group = livestock_groups.get(selected_group_key) if selected_group_key != "Create New Group" else None
            assigned_unit_options = [""] + management_units_df["unit_id"].tolist()
            with st.form("livestock_group_form"):
                group_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                group_name_value = group_cols[0].text_input(
                    "Group Name",
                    value="" if editing_group is None else editing_group.group_name,
                )
                species_value = group_cols[1].selectbox(
                    "Species",
                    options=LIVESTOCK_SPECIES_OPTIONS,
                    index=LIVESTOCK_SPECIES_OPTIONS.index(editing_group.species)
                    if editing_group is not None and editing_group.species in LIVESTOCK_SPECIES_OPTIONS
                    else 0,
                )
                assigned_unit_value = group_cols[2].selectbox(
                    "Assigned Management Unit",
                    options=assigned_unit_options,
                    index=assigned_unit_options.index(editing_group.assigned_unit_id)
                    if editing_group is not None and editing_group.assigned_unit_id in assigned_unit_options
                    else 0,
                    format_func=lambda value: (
                        "Unassigned"
                        if value == ""
                        else f"{value} - {management_units_df.loc[management_units_df['unit_id'] == value, 'name'].iloc[0]}"
                    ),
                )
                group_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                animal_count_value = group_cols[0].number_input(
                    "Animal Count",
                    min_value=0,
                    step=1,
                    value=0 if editing_group is None or editing_group.animal_count is None else int(editing_group.animal_count),
                )
                class_type_value = group_cols[1].text_input(
                    "Class / Type",
                    value="" if editing_group is None else editing_group.class_type,
                    placeholder="Cow-calf pairs, yearlings, broodmares, nannies...",
                )
                average_weight_value = group_cols[2].number_input(
                    "Average Weight",
                    min_value=0.0,
                    step=25.0,
                    value=0.0 if editing_group is None or editing_group.average_weight is None else float(editing_group.average_weight),
                )
                group_notes_value = st.text_area(
                    "Group Notes",
                    value="" if editing_group is None else editing_group.notes,
                    height=100,
                )
                form_cols = responsive_columns([1, 1, 2], field_mode=field_mode, gap="small")
                save_group = form_cols[0].form_submit_button("Save Group")
                delete_group = form_cols[1].form_submit_button("Delete Group")

            if save_group:
                updated_groups = get_livestock_groups()
                updated_overrides = get_management_unit_overrides()
                group_id = editing_group.group_id if editing_group is not None else f"group-{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S%f')}"
                updated_groups[group_id] = LivestockGroup(
                    group_id=group_id,
                    group_name=group_name_value.strip() or ("Unnamed Group" if editing_group is None else editing_group.group_name),
                    species=species_value,
                    animal_count=(None if int(animal_count_value) == 0 else int(animal_count_value)),
                    class_type=class_type_value.strip(),
                    average_weight=(None if float(average_weight_value) == 0 else float(average_weight_value)),
                    assigned_unit_id=(assigned_unit_value or None),
                    notes=group_notes_value.strip(),
                )
                for override in updated_overrides.values():
                    if group_id in override.assigned_group_ids and override.unit_id != assigned_unit_value:
                        override.assigned_group_ids = [value for value in override.assigned_group_ids if value != group_id]
                if assigned_unit_value:
                    target_override = updated_overrides.get(assigned_unit_value, ManagementUnitOverride(unit_id=assigned_unit_value))
                    if group_id not in target_override.assigned_group_ids:
                        target_override.assigned_group_ids.append(group_id)
                    updated_overrides[assigned_unit_value] = target_override
                st.session_state["livestock_groups"] = serialize_livestock_groups(updated_groups)
                st.session_state["management_unit_overrides"] = serialize_management_unit_overrides(updated_overrides)
                st.success("Livestock group saved. Save Current Setup in Settings if you want this persisted for future sessions.")
                st.rerun()

            if delete_group and editing_group is not None:
                updated_groups = get_livestock_groups()
                updated_overrides = get_management_unit_overrides()
                updated_events = get_unit_activity_events()
                updated_groups.pop(editing_group.group_id, None)
                for override in updated_overrides.values():
                    override.assigned_group_ids = [value for value in override.assigned_group_ids if value != editing_group.group_id]
                for event in updated_events.values():
                    if event.livestock_group_id == editing_group.group_id:
                        event.livestock_group_id = None
                st.session_state["livestock_groups"] = serialize_livestock_groups(updated_groups)
                st.session_state["management_unit_overrides"] = serialize_management_unit_overrides(updated_overrides)
                st.session_state["unit_activity_events"] = serialize_unit_activity_events(updated_events)
                st.info("Livestock group deleted.")
                st.rerun()

            st.subheader("Unit Activity Timeline")
            st.caption(
                "Log grazing, rest, turnout, haying, monitoring, or restoration events here so RangeIQ can describe how each management unit is actually being used."
            )
            if activity_log_df.empty:
                st.info("No unit activity has been logged yet. Add an event to track current use, rest windows, or upcoming moves.")
            else:
                render_data_table(prepare_unit_activity_table(activity_log_df))
                month_choices = [pd.Timestamp.today().normalize().replace(day=1) + pd.DateOffset(months=offset) for offset in range(-1, 3)]
                month_labels = {month_start.strftime("%Y-%m"): month_start.strftime("%B %Y") for month_start in month_choices}
                selected_month_key = st.selectbox(
                    "Calendar Month",
                    options=list(month_labels.keys()),
                    index=1,
                    format_func=lambda value: month_labels[value],
                )
                render_activity_calendar(
                    unit_activity_events,
                    livestock_groups,
                    management_units,
                    month_choices[list(month_labels.keys()).index(selected_month_key)],
                    theme,
                )

            activity_choices = ["Create New Activity"] + sorted(unit_activity_events.keys())
            selected_activity_key = st.selectbox(
                "Activity editor",
                options=activity_choices,
                format_func=lambda value: (
                    "Create New Activity"
                    if value == "Create New Activity"
                    else (
                        f"{unit_activity_events[value].activity_type.title()} | "
                        f"{management_units_df.loc[management_units_df['unit_id'] == unit_activity_events[value].unit_id, 'name'].iloc[0]}"
                    )
                ),
            )
            editing_activity = unit_activity_events.get(selected_activity_key) if selected_activity_key != "Create New Activity" else None
            today_value = pd.Timestamp.utcnow().date()
            editing_start_value = pd.to_datetime(editing_activity.start_date).date() if editing_activity and editing_activity.start_date else today_value
            editing_end_value = pd.to_datetime(editing_activity.end_date).date() if editing_activity and editing_activity.end_date else editing_start_value
            event_group_options = [""] + sorted(livestock_groups.keys())
            with st.form("unit_activity_form"):
                activity_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                activity_unit_value = activity_cols[0].selectbox(
                    "Management Unit",
                    options=management_units_df["unit_id"].tolist(),
                    index=management_units_df["unit_id"].tolist().index(editing_activity.unit_id)
                    if editing_activity is not None and editing_activity.unit_id in set(management_units_df["unit_id"])
                    else 0,
                    format_func=lambda value: f"{value} - {management_units_df.loc[management_units_df['unit_id'] == value, 'name'].iloc[0]}",
                )
                activity_type_value = activity_cols[1].selectbox(
                    "Activity Type",
                    options=UNIT_ACTIVITY_TYPE_OPTIONS,
                    index=UNIT_ACTIVITY_TYPE_OPTIONS.index(editing_activity.activity_type)
                    if editing_activity is not None and editing_activity.activity_type in UNIT_ACTIVITY_TYPE_OPTIONS
                    else 0,
                )
                activity_group_value = activity_cols[2].selectbox(
                    "Livestock Group",
                    options=event_group_options,
                    index=event_group_options.index(editing_activity.livestock_group_id or "")
                    if editing_activity is not None and (editing_activity.livestock_group_id or "") in event_group_options
                    else 0,
                    format_func=lambda value: (
                        "No named group"
                        if value == ""
                        else f"{livestock_groups[value].group_name} ({livestock_groups[value].species})"
                    ),
                )
                activity_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                activity_start_date = activity_cols[0].date_input("Start Date", value=editing_start_value)
                use_end_date = activity_cols[1].checkbox(
                    "Specific End Date",
                    value=editing_activity is not None and bool(editing_activity.end_date),
                )
                activity_end_date = activity_cols[2].date_input(
                    "End Date",
                    value=editing_end_value,
                    disabled=not use_end_date,
                )
                activity_notes_value = st.text_area(
                    "Activity Notes",
                    value="" if editing_activity is None else editing_activity.notes,
                    height=100,
                    placeholder="Rotation window, turnout limits, targeted browse objective, hay cut notes, restoration work, or monitoring context...",
                )
                form_cols = responsive_columns([1, 1, 2], field_mode=field_mode, gap="small")
                save_activity = form_cols[0].form_submit_button("Save Activity")
                delete_activity = form_cols[1].form_submit_button("Delete Activity")

            if save_activity:
                if use_end_date and activity_end_date < activity_start_date:
                    st.error("End date cannot be earlier than the start date.")
                else:
                    updated_events = get_unit_activity_events()
                    event_id = editing_activity.event_id if editing_activity is not None else f"activity-{uuid4().hex[:10]}"
                    updated_events[event_id] = UnitActivityEvent(
                        event_id=event_id,
                        unit_id=activity_unit_value,
                        activity_type=activity_type_value,
                        livestock_group_id=(activity_group_value or None),
                        start_date=activity_start_date.isoformat(),
                        end_date=(activity_end_date.isoformat() if use_end_date else None),
                        notes=activity_notes_value.strip(),
                    )
                    st.session_state["unit_activity_events"] = serialize_unit_activity_events(updated_events)
                    st.success("Unit activity saved. Save Current Setup in Settings if you want this persisted for future sessions.")
                    st.rerun()

            if delete_activity and editing_activity is not None:
                updated_events = get_unit_activity_events()
                updated_events.pop(editing_activity.event_id, None)
                st.session_state["unit_activity_events"] = serialize_unit_activity_events(updated_events)
                st.info("Unit activity deleted.")
                st.rerun()

            st.subheader("Unit Assignment Overview")
            assignment_df = management_units_df[
                [
                    "unit_id",
                    "name",
                    "unit_type",
                    "assigned_groups",
                    "assigned_livestock",
                    "current_activity",
                    "current_status",
                    "recent_activity",
                    "attention_level",
                    "recommendation",
                    "notes",
                ]
            ].copy()
            render_data_table(
                prepare_attention_queue_table(
                    assignment_df.rename(columns={"assigned_groups": "Assigned Groups"})
                )
            )

            st.subheader("Unit Utilization / Recovery Outlook")
            st.caption(
                "RangeIQ estimates recent use pressure with a simple 30-day animal-unit-days-per-acre heuristic. Treat this as a planning signal, not a forage inventory substitute."
            )
            if unit_utilization_df.empty:
                st.info("No unit utilization summary is available yet.")
            else:
                render_data_table(prepare_unit_utilization_table(unit_utilization_df))

    if data_shell is not None:
        with data_shell:
            source_card_cols = responsive_columns(4, field_mode=field_mode, gap="medium")
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
                        "Component": "Unit Intelligence",
                        "Configured provider": "synthetic",
                        "Active provider": "synthetic",
                        "Mode": "synthetic",
                        "Status": "The current scoring engine still starts from pasture-week features underneath the broader ranch-intelligence interface.",
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
                            f"{artifacts.training_dataset_summary['pastures']} mapped unit(s) and "
                            f"{artifacts.training_dataset_summary['weeks']} week(s)."
                        ),
                        "Last updated": format_timestamp(last_updated),
                        "Citation": "RangeIQ hybrid training dataset",
                    },
                ]
            )
            provider_rows = pd.DataFrame(provider_rows)
            render_data_table(provider_rows)

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
            render_data_table(file_rows)

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
                    "ranch_profile": runtime_settings.ranch_profile.__dict__,
                    "field_feedback_count": len(unit_feedback_labels),
                    "unit_activity_event_count": len(unit_activity_events),
                    "shadow_review_rows": int(feedback_shadow_review_summary["rows"]),
                }
            )

            st.subheader("Hybrid Training Dataset Summary")
            st.json(artifacts.training_dataset_summary)

            st.subheader("Field Feedback Dataset Summary")
            st.caption(
                "These saved field labels are not yet merged into the current production model training loop, but they are now structured for future model review and calibration work."
            )
            st.json(feedback_dataset_summary)
            if feedback_dataset_df.empty:
                st.info("No field feedback labels have been logged yet.")
            else:
                render_data_table(
                    feedback_dataset_df.rename(
                        columns={
                            "observed_on": "Observed On",
                            "unit_name": "Unit",
                            "unit_type": "Unit Type",
                            "unit_acres": "Acres",
                            "label_type": "Label Type",
                            "label_value": "Observed Value",
                            "confidence": "Confidence",
                            "assigned_group_names": "Assigned Groups",
                            "assigned_livestock": "Assigned Livestock",
                            "management_style": "Management Style",
                        }
                    )[
                        [
                            "Observed On",
                            "Unit",
                            "Unit Type",
                            "Acres",
                            "Label Type",
                            "Observed Value",
                            "Confidence",
                            "Assigned Groups",
                            "Assigned Livestock",
                            "Management Style",
                            "notes",
                        ]
                    ].rename(columns={"notes": "Notes"})
                )
                st.download_button(
                    "Download Field Feedback CSV",
                    data=feedback_dataset_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{CURRENT_WORKSPACE_ID}_field_feedback.csv",
                    mime="text/csv",
                )

            st.subheader("Feedback Calibration Dataset")
            st.caption(
                "RangeIQ now maps field labels into candidate numeric or classification targets for shadow-model review. These are suggestions for future calibration work, not live production targets yet."
            )
            st.json(feedback_calibration_summary)
            if feedback_calibration_df.empty:
                st.info("No calibration-ready feedback targets are available yet.")
            else:
                render_data_table(
                    feedback_calibration_df.rename(
                        columns={
                            "observed_on": "Observed On",
                            "unit_name": "Unit",
                            "label_type": "Label Type",
                            "label_value": "Observed Value",
                            "target_family": "Target Family",
                            "target_type": "Target Type",
                            "candidate_numeric_target": "Numeric Target",
                            "candidate_class_target": "Class Target",
                            "confidence": "Confidence",
                            "confidence_weight": "Weight",
                            "management_style": "Management Style",
                            "ranch_type": "Ranch Type",
                            "notes": "Notes",
                        }
                    )[
                        [
                            "Observed On",
                            "Unit",
                            "Label Type",
                            "Observed Value",
                            "Target Family",
                            "Target Type",
                            "Numeric Target",
                            "Class Target",
                            "Confidence",
                            "Weight",
                            "Management Style",
                            "Ranch Type",
                            "Notes",
                        ]
                    ]
                )
                st.download_button(
                    "Download Calibration CSV",
                    data=feedback_calibration_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{CURRENT_WORKSPACE_ID}_feedback_calibration.csv",
                    mime="text/csv",
                )

            st.subheader("Shadow Review Against Current Model")
            st.caption(
                "This compares saved calibration labels against the current live RangeIQ outputs for each unit. It is a review layer only and does not modify the production model."
            )
            st.json(feedback_shadow_review_summary)
            if feedback_shadow_review_df.empty:
                st.info("No shadow-review comparisons are available yet.")
            else:
                render_data_table(
                    feedback_shadow_review_df.rename(
                        columns={
                            "observed_on": "Observed On",
                            "unit_name": "Unit",
                            "target_family": "Target Family",
                            "target_type": "Target Type",
                            "candidate_numeric_target": "Candidate Numeric Target",
                            "candidate_class_target": "Candidate Class Target",
                            "live_signal_source": "Live Signal Source",
                            "live_numeric_signal": "Live Numeric Signal",
                            "live_class_signal": "Live Class Signal",
                            "delta": "Delta",
                            "absolute_error": "Absolute Error",
                            "class_match": "Class Match",
                            "confidence": "Confidence",
                            "confidence_weight": "Weight",
                            "management_style": "Management Style",
                            "ranch_type": "Ranch Type",
                            "notes": "Notes",
                        }
                    )[
                        [
                            "Observed On",
                            "Unit",
                            "Target Family",
                            "Target Type",
                            "Candidate Numeric Target",
                            "Candidate Class Target",
                            "Live Signal Source",
                            "Live Numeric Signal",
                            "Live Class Signal",
                            "Delta",
                            "Absolute Error",
                            "Class Match",
                            "Confidence",
                            "Weight",
                            "Management Style",
                            "Ranch Type",
                            "Notes",
                        ]
                    ]
                )
                st.download_button(
                    "Download Shadow Review CSV",
                    data=feedback_shadow_review_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{CURRENT_WORKSPACE_ID}_feedback_shadow_review.csv",
                    mime="text/csv",
                )

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

    if settings_shell is not None:
        with settings_shell:
            st.markdown(
                "<div class='rq-section-intro'>Use this control center to tune the ranch profile, public-data mix, alert thresholds, and saved workspace behavior.</div>",
                unsafe_allow_html=True,
            )
            workspace_settings_tab, provider_settings_tab, safety_settings_tab, diagnostics_settings_tab = st.tabs(
                ["Ranch Profile", "Providers", "Operations & Save", "Diagnostics"]
            )

            with workspace_settings_tab:
                boundary_save_mode = "current upload" if boundary_mode == "uploaded" else "saved boundary" if boundary_mode == "saved" else "default corners"
                account_cols = responsive_columns([1, 1, 0.8], field_mode=field_mode, gap="medium")
                with account_cols[0]:
                    render_signal_card(
                        title="Account",
                        value=CURRENT_USER.full_name,
                        subtitle=CURRENT_USER.email,
                        badges=[highlight_badge("info", "SIGNED IN")],
                    )
                with account_cols[1]:
                    render_signal_card(
                        title="Workspace",
                        value="Private",
                        subtitle=f"{CURRENT_WORKSPACE_ID} | Reopens with {boundary_save_mode}.",
                        badges=[highlight_badge("success", "PERSISTED")],
                    )
                with account_cols[2]:
                    st.markdown("<div class='rq-control-kicker'>Session</div>", unsafe_allow_html=True)
                    st.markdown("<div class='rq-control-title'>Access</div>", unsafe_allow_html=True)
                    st.markdown(
                        "<div class='rq-control-copy'>Sign out here if you want to switch ranch accounts on this device.</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button("Log Out"):
                        sign_out_user()
                        st.rerun()

                st.subheader("Ranch Identity")
                ranch_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                ranch_cols[0].text_input("Ranch Name", key="ranch_name")
                ranch_cols[1].text_input("Ranch Address", key="ranch_address")
                ranch_cols = responsive_columns(3, field_mode=field_mode, gap="small")
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

                st.subheader("Operating Profile")
                profile_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                profile_cols[0].selectbox("Ranch Type", options=RANCH_TYPE_OPTIONS, key="ranch_type")
                profile_cols[1].selectbox("Management Style", options=MANAGEMENT_STYLE_OPTIONS, key="management_style")
                profile_cols[2].selectbox("Preferred Unit Terminology", options=["management unit", "pasture", "paddock", "field", "turnout", "block"], key="preferred_unit_term")
                profile_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                profile_cols[0].selectbox("Default Management Unit Type", options=MANAGEMENT_UNIT_TYPE_OPTIONS, key="default_unit_type")
                profile_cols[1].toggle("This ranch rotates animals", key="rotates_animals")
                st.multiselect(
                    "Primary Livestock Species",
                    options=LIVESTOCK_SPECIES_OPTIONS,
                    key="livestock_species",
                    help="Use wildlife/no livestock if this workspace is strictly for land monitoring.",
                )
                st.multiselect(
                    "Primary Goals",
                    options=RANCH_GOAL_OPTIONS,
                    key="primary_goals",
                    help="These goals help RangeIQ choose better language and emphasis across the dashboard.",
                )
                st.text_area(
                    "Ranch Notes",
                    key="ranch_profile_notes",
                    height=110,
                    help="Optional context for this workspace, such as operating constraints, lease notes, or restoration objectives.",
                )
                st.caption(
                    "This profile is saved with the workspace so the dashboard can speak in the right language for rotational grazing, continuous grazing, horses, goats, sheep, hay, restoration, or land-only monitoring."
                )

            with provider_settings_tab:
                st.subheader("Operational Providers")
                provider_cols = responsive_columns(2, field_mode=field_mode, gap="small")
                provider_cols[0].selectbox("Weather Provider", options=["mock", "nws", "openmeteo"], key="weather_provider")
                provider_cols[1].selectbox("Alert Provider", options=["mock", "nws"], key="alerts_provider")

                st.subheader("Public Data Providers")
                public_provider_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                public_provider_cols[0].selectbox("Historical Weather", options=["mock", "nasa_power"], key="historical_weather_provider")
                public_provider_cols[1].selectbox("Soils", options=["mock", "usda_sda"], key="soils_provider")
                public_provider_cols[2].selectbox("Drought", options=["mock", "usdm"], key="drought_provider")
                cache_cols = responsive_columns(5, field_mode=field_mode, gap="small")
                cache_cols[0].toggle("Enable Public Cache", key="public_cache_enabled")
                cache_cols[1].number_input("Weather Refresh (h)", min_value=1, step=12, key="historical_weather_refresh_hours")
                cache_cols[2].number_input("Soils Refresh (h)", min_value=1, step=24, key="soils_refresh_hours")
                cache_cols[3].number_input("Drought Refresh (h)", min_value=1, step=12, key="drought_refresh_hours")
                cache_cols[4].number_input("Vegetation Refresh (h)", min_value=1, step=24, key="vegetation_refresh_hours")
                st.selectbox("Vegetation", options=["mock", "earth_search_stac", "climate_engine"], key="vegetation_provider")
                st.caption(
                    "Public historical sources are cached on disk so RangeIQ can reuse them offline and avoid unnecessary refreshes. "
                    "Vegetation history now combines Earth Search STAC NDVI with RAP. Earth Search STAC is the default live NDVI source, "
                    "and Climate Engine remains optional. If live vegetation providers fail, RangeIQ falls back to mock history."
                )

                st.subheader("Sensor Stack")
                st.info(
                    "Sensor monitoring and sensor-network controls are currently under development. "
                    "They are paused in the hosted dashboard while we improve performance and finish the next implementation pass."
                )

            with safety_settings_tab:
                st.subheader("Fire Risk Thresholds")
                fire_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                fire_cols[0].number_input("High Wind (mph)", min_value=5, step=1, key="high_wind_mph")
                fire_cols[1].number_input("High Gust (mph)", min_value=10, step=1, key="high_gust_mph")
                fire_cols[2].number_input("Low Humidity (%)", min_value=5, max_value=60, step=1, key="low_humidity_pct")
                fire_cols = responsive_columns(3, field_mode=field_mode, gap="small")
                fire_cols[0].number_input("High Temperature (F)", min_value=60, max_value=120, step=1, key="high_temperature_f")
                fire_cols[1].number_input("Low Rainfall 7d (in)", min_value=0.0, max_value=2.0, step=0.01, format="%.2f", key="low_rainfall_7d_in")
                fire_cols[2].number_input("Low Soil Moisture (%)", min_value=1, max_value=50, step=1, key="low_soil_moisture_pct")

                st.subheader("Save This Setup")
                st.caption(
                    "Save writes your current ranch profile, management-unit metadata, provider selections, uploaded boundary reference, and field feedback labels to the workspace config/state "
                    "so RangeIQ can reopen with the same setup next time. Livestock groups and unit activity timelines are included too."
                )
                save_cols = responsive_columns([1, 2], field_mode=field_mode, gap="medium")
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
                        st.markdown(
                            f"Current workspace: **{CURRENT_WORKSPACE_ID}**. "
                            f"Reopen state: **{boundary_save_mode}**. "
                            "Providers, ranch identity, ranch profile, map settings, time horizon, and thresholds are saved to this account."
                            " Custom management-unit names, types, livestock assignments, activity timelines, field feedback labels, and notes are saved too."
                        )

            with diagnostics_settings_tab:
                st.subheader("Current Effective Config")
                preview_settings = build_runtime_settings()
                st.json(preview_settings.to_display_dict())

                st.subheader("Saved Management Unit Overrides")
                st.json(st.session_state.get("management_unit_overrides", {}))

                st.subheader("Saved Livestock Groups")
                st.json(st.session_state.get("livestock_groups", {}))

                st.subheader("Saved Unit Activity Events")
                st.json(st.session_state.get("unit_activity_events", {}))

                st.subheader("Saved Field Feedback Labels")
                st.json(st.session_state.get("unit_feedback_labels", {}))

                st.subheader("Field Feedback Model-Prep Summary")
                st.json(feedback_dataset_summary)

                st.subheader("Calibration Target Summary")
                st.json(feedback_calibration_summary)

                st.subheader("Shadow Review Summary")
                st.json(feedback_shadow_review_summary)

                st.subheader("Saved Model Status")
                st.json(artifacts.model_storage_summary)

                with st.expander("AI Model Window"):
                    st.write(f"Selected forage regressor: `{artifacts.selected_forage_model}`")
                    st.json(artifacts.model_metrics["forage_model"])
                    st.text(artifacts.model_metrics["stress_model"]["report"])
