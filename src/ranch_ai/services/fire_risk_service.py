from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.optimization.risk_rules import FIRE_ALERT_EVENTS, drought_rank, fire_risk_category, fire_risk_color


@dataclass
class FireRiskAssessment:
    score: float
    category: str
    color: str
    main_drivers: list[str]
    recommended_actions: list[str]
    weather_inputs: dict[str, Any]
    disclaimer: str


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _rainfall_mm_to_in(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 25.4


def _worst_drought_category(latest_snapshot: pd.DataFrame) -> str | None:
    if latest_snapshot.empty or "drought_category" not in latest_snapshot.columns:
        return None
    categories = latest_snapshot["drought_category"].dropna().astype(str)
    if categories.empty:
        return None
    return max(categories, key=drought_rank)


def assess_fire_risk(
    current_weather: dict[str, Any],
    alerts_df: pd.DataFrame,
    latest_snapshot: pd.DataFrame,
    sensor_status_df: pd.DataFrame,
    sensor_readings_df: pd.DataFrame | None = None,
    app_settings: Settings = settings,
) -> FireRiskAssessment:
    cfg = app_settings.fire_risk
    score = 10.0
    drivers: list[str] = []
    actions: list[str] = []

    temperature_f = _safe_float(current_weather.get("temperature_f"))
    humidity_pct = _safe_float(current_weather.get("humidity_pct"))
    wind_speed_mph = _safe_float(current_weather.get("wind_speed_mph"))
    wind_gust_mph = _safe_float(current_weather.get("wind_gust_mph"))
    rainfall_today_in = _safe_float(current_weather.get("rainfall_expected_today_in"))

    if humidity_pct is not None and humidity_pct < cfg.low_humidity_pct:
        score += 22 if humidity_pct < 15 else 16
        drivers.append(f"Low humidity ({humidity_pct:.0f}%)")
        actions.append("Avoid welding, burning, or spark-generating work.")

    if wind_speed_mph is not None and wind_speed_mph > cfg.high_wind_mph:
        score += 18 if wind_speed_mph < 30 else 24
        drivers.append(f"High sustained wind ({wind_speed_mph:.0f} mph)")
        actions.append("Inspect high-risk pastures and postpone roadside hot work.")

    if wind_gust_mph is not None and wind_gust_mph > cfg.high_gust_mph:
        score += 10 if wind_gust_mph < 40 else 15
        drivers.append(f"High wind gusts ({wind_gust_mph:.0f} mph)")

    if temperature_f is not None and temperature_f > cfg.high_temperature_f:
        score += 8 if temperature_f < 100 else 12
        drivers.append(f"Hot conditions ({temperature_f:.0f} F)")
        actions.append("Check water tanks, troughs, and livestock heat-stress areas.")

    avg_rainfall_7d_in = None
    if not latest_snapshot.empty and "rainfall_7d" in latest_snapshot.columns:
        avg_rainfall_7d_in = _rainfall_mm_to_in(float(latest_snapshot["rainfall_7d"].mean()))
        if avg_rainfall_7d_in is not None and avg_rainfall_7d_in < cfg.low_rainfall_7d_in:
            score += 12
            drivers.append("Very low rainfall over the last 7 days")

    worst_drought = _worst_drought_category(latest_snapshot)
    drought_level = drought_rank(worst_drought)
    if drought_level >= 2:
        score += 10 + (drought_level - 2) * 5
        drivers.append(f"Drought category {worst_drought}")
        actions.append("Review contingency grazing and supplementation plans.")

    avg_ndvi_anomaly = None
    if not latest_snapshot.empty and "ndvi_anomaly" in latest_snapshot.columns:
        avg_ndvi_anomaly = float(latest_snapshot["ndvi_anomaly"].mean())
        if avg_ndvi_anomaly < -0.08:
            score += 6
            drivers.append(f"Below-normal vegetation signal ({avg_ndvi_anomaly:.2f})")

    avg_soil_moisture_30 = None
    if not sensor_status_df.empty and "soil_moisture_30cm" in sensor_status_df.columns:
        avg_soil_moisture_30 = float(sensor_status_df["soil_moisture_30cm"].dropna().mean())
        if avg_soil_moisture_30 < cfg.low_soil_moisture_pct:
            score += 14
            drivers.append(f"Low deep soil moisture ({avg_soil_moisture_30:.1f}%)")

    rainfall_14d_in = None
    if sensor_readings_df is not None and not sensor_readings_df.empty:
        recent_cutoff = pd.Timestamp.now() - pd.Timedelta(days=14)
        recent_readings = sensor_readings_df.loc[sensor_readings_df["timestamp"] >= recent_cutoff].copy()
        if not recent_readings.empty and "rainfall_in" in recent_readings.columns:
            by_station = recent_readings.groupby("station_id", as_index=False)["rainfall_in"].sum()
            rainfall_14d_in = float(by_station["rainfall_in"].mean())
            if rainfall_14d_in < max(cfg.low_rainfall_7d_in * 2, 0.08):
                score += 8
                drivers.append("Little to no rainfall in the last 14 days")

    if not alerts_df.empty and "event" in alerts_df.columns:
        events = set(alerts_df["event"].astype(str))
        if "Red Flag Warning" in events:
            score = max(score, 88)
            drivers.append("Active Red Flag Warning")
            actions.append("Stage fire response contacts and keep vehicles out of tall dry grass.")
        elif "Fire Weather Watch" in events:
            score = max(score, 72)
            drivers.append("Active Fire Weather Watch")

        if any(event in {"Severe Thunderstorm Warning", "High Wind Warning"} for event in events):
            actions.append("Inspect sensor stations and solar battery status before severe weather.")

    if not sensor_status_df.empty:
        low_water_count = int((sensor_status_df["water_tank_pct"].fillna(100) < 25).sum())
        offline_count = int(sensor_status_df["status"].isin(["OFFLINE", "STALE"]).sum())
        if low_water_count > 0:
            score += 5
            drivers.append(f"{low_water_count} station(s) reporting low water storage")
        if offline_count > 0:
            actions.append("Check offline or stale stations before the next wind or fire event.")

    if rainfall_today_in is not None and rainfall_today_in >= 0.25:
        score -= 6

    score = max(0.0, min(100.0, round(score, 1)))
    category = fire_risk_category(score)
    color = fire_risk_color(category)

    if category in {"VERY HIGH", "EXTREME"}:
        actions.append("Prepare emergency contact list and access routes.")
    if category in {"HIGH", "VERY HIGH", "EXTREME"}:
        actions.append("Avoid driving over tall dry grass and inspect high-risk pastures.")

    unique_actions = list(dict.fromkeys(actions))
    if not unique_actions:
        unique_actions = ["Continue routine monitoring and follow official forecasts and alerts."]

    unique_drivers = list(dict.fromkeys(drivers))
    if not unique_drivers:
        unique_drivers = ["No major fire-weather triggers detected in the current operational snapshot."]

    return FireRiskAssessment(
        score=score,
        category=category,
        color=color,
        main_drivers=unique_drivers[:5],
        recommended_actions=unique_actions[:5],
        weather_inputs={
            "temperature_f": temperature_f,
            "humidity_pct": humidity_pct,
            "wind_speed_mph": wind_speed_mph,
            "wind_gust_mph": wind_gust_mph,
            "rainfall_expected_today_in": rainfall_today_in,
            "avg_rainfall_7d_in": avg_rainfall_7d_in,
            "rainfall_14d_in": rainfall_14d_in,
            "avg_soil_moisture_30cm": avg_soil_moisture_30,
            "worst_drought_category": worst_drought,
            "has_fire_alert": bool(
                not alerts_df.empty and set(alerts_df["event"].astype(str)).intersection(FIRE_ALERT_EVENTS)
            ),
        },
        disclaimer=(
            "Decision support only. Always follow official warnings, fire authorities, and evacuation instructions."
        ),
    )
