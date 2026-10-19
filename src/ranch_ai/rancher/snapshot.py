"""Build the phone app's ranch snapshot from OBSERVED data (runs in the nightly worker).

The snapshot is one JSON document per ranch: ranch info, data sources with
dates, current weather and 7-day forecast, NWS alerts, fire danger, and one
entry per pasture with its outline, Good/Watch/Act status, the signals behind
it, and a terrain summary.

Rule: a value from a mock or fallback provider is never shown as real.
Unless ``demo=True`` (a clearly labeled sample ranch), such inputs become
"not available".
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ranch_ai.config import Settings
from ranch_ai.rancher.status import (
    combine,
    drought_signal,
    grass_signal,
    occupancy_signal,
    rain_signal,
    range_trend_signal,
)

LIVE_MODES = {"real", "cached", "stale-cache", "live", "live-cached"}
NDVI_HISTORY_YEARS = 5
SNAPSHOT_VERSION = 1


def is_live(mode: str | None) -> bool:
    return str(mode or "").lower() in LIVE_MODES


def _num(value: Any, digits: int = 1) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def rain_totals(history: pd.DataFrame, *, min_years: int = 3) -> dict[str, Any]:
    """90/30-day rain to the last observed day, and the 90-day normal from the same window in prior years."""
    if history is None or history.empty or "public_precip_in" not in history:
        return {}
    df = history[["date", "public_precip_in"]].dropna().copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df.groupby("date", as_index=True)["public_precip_in"].sum().sort_index()
    if df.empty:
        return {}
    end = df.index.max()

    def window_sum(stop: pd.Timestamp, days: int) -> float | None:
        window = df.loc[(df.index > stop - pd.Timedelta(days=days)) & (df.index <= stop)]
        return float(window.sum()) if len(window) >= days * 0.8 else None

    rain_90 = window_sum(end, 90)
    rain_30 = window_sum(end, 30)
    prior = []
    for years_back in range(1, 31):
        stop = end - pd.DateOffset(years=years_back)
        if stop < df.index.min():
            break
        value = window_sum(stop, 90)
        if value is not None:
            prior.append(value)
    normal_90 = float(np.mean(prior)) if len(prior) >= min_years else None
    return {
        "rain_90d_in": _num(rain_90, 2),
        "rain_30d_in": _num(rain_30, 2),
        "normal_90d_in": _num(normal_90, 2),
        "normal_years": len(prior),
        "as_of": end.strftime("%Y-%m-%d"),
    }


PROVIDER_NAMES = {
    "nasa_power": "NASA POWER", "nws": "National Weather Service", "openmeteo": "Open-Meteo", "usdm": "U.S. Drought Monitor",
    "usda_sda": "USDA Soil Survey", "earth_search_stac": "Sentinel-2 (Earth Search)", "rap": "RAP", "usgs_3dep": "USGS 3DEP",
}


def friendly_provider(provider: str | None, mode: str | None, demo: bool) -> str | None:
    if not is_live(mode):
        return "Demo" if demo else None
    if not provider:
        return None
    return PROVIDER_NAMES.get(str(provider).lower(), str(provider))


def _source_entry(name: str, mode: str | None, provider: str | None, as_of: str | None, demo: bool,
                  note: str | None = None) -> dict[str, Any]:
    live = is_live(mode)
    return {
        "note": None if live and mode != "stale-cache" else (str(note)[:300] if note else None),
        "name": name,
        "provider": friendly_provider(provider, mode, demo),
        "live": live,
        "stale": str(mode or "") == "stale-cache",
        "demo": (not live) and demo,
        "as_of": as_of,
        "mode": mode,
    }


def _rancher_text(text: Any) -> str | None:
    """Drop advice about the (paused) sensor network; ranchers can't act on it."""
    if not text:
        return None
    text = str(text)
    return None if "sensor" in text.lower() else text


def _ring(geometry: Any) -> list[list[float]]:
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    return [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in geometry]


def build_snapshot(
    app_settings: Settings,
    pastures: pd.DataFrame,
    *,
    logs: list[dict[str, Any]] | None = None,
    history_years: int = 10,
    demo: bool = False,
    include_terrain: bool = True,
    terrain_result: Any = None,
    today: pd.Timestamp | None = None,
) -> dict[str, Any]:
    from ranch_ai.rancher.store import herd_days_by_pasture
    from ranch_ai.services.alert_service import AlertService
    from ranch_ai.services.fire_risk_service import assess_fire_risk
    from ranch_ai.services.public_data_service import PublicDataService
    from ranch_ai.services.weather_service import WeatherService

    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    lat = float(pastures["centroid_lat"].mean())
    lon = float(pastures["centroid_lon"].mean())
    sources: list[dict[str, Any]] = []

    def usable(mode: str | None) -> bool:
        return is_live(mode) or demo

    # Weather and alerts (operational) ------------------------------------------------
    weather_service = WeatherService(app_settings)
    weather_bundle = weather_service.load_weather_bundle(lat, lon)
    if not is_live(weather_bundle.mode):
        # Try the other live forecast service before giving up on weather.
        configured = str(app_settings.weather.provider).lower()
        for alternative in ("nws", "openmeteo"):
            if alternative == configured:
                continue
            second = weather_service.load_weather_bundle(lat, lon, provider=alternative)
            if is_live(second.mode):
                weather_bundle = second
                break
    sources.append(_source_entry("Weather forecast", weather_bundle.mode, weather_bundle.provider_name,
                                 _date(weather_bundle.loaded_at), demo))
    weather: dict[str, Any] | None = None
    if usable(weather_bundle.mode):
        cur = weather_bundle.current
        forecast = []
        for row in weather_bundle.forecast.head(7).to_dict("records"):
            forecast.append({
                "date": _date(row.get("date")),
                "label": row.get("weather_label") or "",
                "high_f": _num(row.get("high_temp_f"), 0),
                "low_f": _num(row.get("low_temp_f"), 0),
                "rain_chance_pct": _num(row.get("precip_probability_pct"), 0),
                "rain_in": _num(row.get("expected_precip_in"), 2),
                "wind_mph": _num(row.get("wind_speed_mph"), 0),
                "gust_mph": _num(row.get("wind_gust_mph"), 0),
            })
        weather = {
            "temp_f": _num(cur.temperature_f, 0),
            "feels_like_f": _num(cur.feels_like_f, 0),
            "humidity_pct": _num(cur.humidity_pct, 0),
            "wind_mph": _num(cur.wind_speed_mph, 0),
            "gust_mph": _num(cur.wind_gust_mph, 0),
            "wind_dir": cur.wind_direction,
            "label": cur.weather_label,
            "observed_at": pd.Timestamp(cur.observation_time).isoformat() if cur.observation_time is not None else None,
            "forecast": forecast,
        }

    alert_bundle = AlertService(app_settings).load_alert_bundle(lat, lon)
    sources.append(_source_entry("Weather alerts", alert_bundle.mode, "NWS" if is_live(alert_bundle.mode) else alert_bundle.provider_name,
                                 _date(alert_bundle.loaded_at), demo))
    alerts: list[dict[str, Any]] | None = None
    if usable(alert_bundle.mode):
        alerts = [
            {
                "event": row.get("event"),
                "headline": row.get("headline"),
                "severity": row.get("severity"),
                "expires": pd.Timestamp(row["expires"]).isoformat() if pd.notna(row.get("expires")) else None,
                "what_it_means": _rancher_text(row.get("operational_concern")),
                "fire_weather": bool(row.get("is_fire_weather")),
            }
            for row in alert_bundle.alerts.to_dict("records")
        ]

    fire: dict[str, Any] | None = None
    if weather is not None:
        assessment = assess_fire_risk(
            current_weather=WeatherService.current_as_dict(weather_bundle),
            alerts_df=alert_bundle.alerts if alerts is not None else pd.DataFrame(),
            latest_snapshot=pd.DataFrame(),
            sensor_status_df=pd.DataFrame(),
            app_settings=app_settings,
        )
        drivers = [d for d in assessment.main_drivers if _rancher_text(d) and "No major fire-weather" not in d]
        actions = [a for a in assessment.recommended_actions if _rancher_text(a)]
        fire = {"level": assessment.category, "drivers": drivers[:3], "actions": actions[:2]}

    # Rain, drought, greenness, range trend --------------------------------------------
    # Rain history needs ~10 years (for normals); drought and soils ride along.
    bundle = PublicDataService(app_settings).load_public_data_bundle(
        pastures=pastures,
        start_date=today - pd.DateOffset(years=history_years) - pd.Timedelta(days=100),
        end_date=today,
        history_years=history_years,
        include_vegetation=False,
    )
    # Greenness gets its own window: the last 6 months plus NDVI_HISTORY_YEARS of monthly normals
    # (Sentinel-2 starts in 2015). The end is rounded to the start of the week so the expensive
    # satellite pull is cached and reused by every hourly run that week.
    from ranch_ai.vegetation.vegetation_service import VegetationService

    veg_end = (today - pd.Timedelta(days=int(today.weekday()))).normalize()
    vegetation_artifacts, vegetation_statuses = VegetationService(app_settings).build_artifacts(
        pastures,
        start_date=veg_end - pd.DateOffset(months=6),
        end_date=veg_end,
        history_years=NDVI_HISTORY_YEARS,
    )
    bundle.vegetation_artifacts = vegetation_artifacts
    bundle.source_status.extend(vegetation_statuses)
    modes = {status.component: status for status in bundle.source_status}

    hw = modes.get("Historical Weather")
    rain = rain_totals(bundle.historical_weather) if hw and usable(hw.mode) else {}
    sources.append(_source_entry("Rain history", hw.mode if hw else None, hw.active_provider if hw else None, rain.get("as_of"), demo,
                                 hw.status if hw else None))

    dr = modes.get("Drought")
    drought_cat, drought_asof = None, None
    if dr and usable(dr.mode) and not bundle.drought.empty:
        latest = bundle.drought.sort_values("week_start").iloc[-1]
        drought_cat, drought_asof = latest.get("public_usdm_category"), _date(latest.get("week_start"))
    sources.append(_source_entry("U.S. Drought Monitor", dr.mode if dr else None, dr.active_provider if dr else None, drought_asof, demo,
                                 dr.status if dr else None))

    nd = modes.get("Vegetation NDVI")
    rp = modes.get("Vegetation RAP")
    va = bundle.vegetation_artifacts
    summary = va.summary_frame.set_index("pasture_id") if va is not None and not va.summary_frame.empty else pd.DataFrame()
    ndvi_asof: dict[str, str | None] = {}
    if va is not None and not va.ndvi_series.empty and "date" in va.ndvi_series:
        for pid, group in va.ndvi_series.groupby("pasture_id"):
            ndvi_asof[str(pid)] = _date(group["date"].max())
    sources.append(_source_entry("Satellite greenness (Sentinel-2)", nd.mode if nd else None, nd.active_provider if nd else None,
                                 max((d for d in ndvi_asof.values() if d), default=None), demo, nd.status if nd else None))
    rap_year = None
    if not summary.empty and "rap_latest_year" in summary:
        rap_year = summary["rap_latest_year"].dropna().max() if summary["rap_latest_year"].notna().any() else None
    sources.append(_source_entry("Rangeland Analysis Platform", rp.mode if rp else None, rp.active_provider if rp else None,
                                 str(int(rap_year)) if rap_year is not None else None, demo, rp.status if rp else None))

    # Terrain (cached lidar DEM) ---------------------------------------------------------
    terrain_by_pasture: dict[str, dict[str, Any]] = {}
    if include_terrain:
        try:
            from ranch_ai.terrain import TerrainService, compute_derivatives, pasture_terrain_stats

            result = terrain_result if terrain_result is not None else TerrainService(app_settings).load(pastures)
            terrain_mode = str(result.status.get("mode"))
            sources.append(_source_entry("USGS 3DEP lidar elevation", terrain_mode, "usgs_3dep", None, demo))
            if usable(terrain_mode):
                stats = pasture_terrain_stats(result.grid, pastures,
                                              grazing_slope_window_m=app_settings.terrain.grazing_slope_window_m,
                                              derivatives=compute_derivatives(result.grid))
                for row in stats.to_dict("records"):
                    terrain_by_pasture[str(row["pasture_id"])] = {
                        "elev_min_ft": _num(row.get("elev_min_ft"), 0),
                        "elev_max_ft": _num(row.get("elev_max_ft"), 0),
                        "relief_ft": _num(row.get("relief_ft"), 0),
                        "mean_slope_pct": _num(row.get("slope_mean_pct_grazing"), 1),
                        "steep_share_pct": _num((row.get("share_slope_31-60%") or 0) + (row.get("share_slope_>60%") or 0), 1),
                        "faces": row.get("dominant_aspect"),
                        "slope_adjusted_acres": _num(row.get("slope_adjusted_acres"), 1),
                    }
        except Exception as exc:  # noqa: BLE001 - terrain is optional
            sources.append({"name": "USGS 3DEP lidar elevation", "live": False, "demo": False, "error": str(exc)[:200]})

    # Pastures ---------------------------------------------------------------------------
    herd = herd_days_by_pasture(logs or [], today=datetime.now(timezone.utc))
    out_pastures = []
    for record in pastures.to_dict("records"):
        pid = str(record["pasture_id"])
        veg = summary.loc[pid] if pid in summary.index else None
        signals = [
            rain_signal(rain.get("rain_90d_in"), rain.get("normal_90d_in"), rain.get("rain_30d_in"),
                        source=friendly_provider(hw.active_provider if hw else None, hw.mode if hw else None, demo), as_of=rain.get("as_of")),
            grass_signal(_num(veg.get("ndvi_anomaly_percent"), 0) if veg is not None and nd and usable(nd.mode) else None,
                         source=friendly_provider("earth_search_stac", nd.mode if nd else None, demo), as_of=ndvi_asof.get(pid)),
            drought_signal(drought_cat, source=friendly_provider("usdm", dr.mode if dr else None, demo), as_of=drought_asof),
            range_trend_signal(
                veg.get("rap_perennial_grass_trend") if veg is not None and rp and usable(rp.mode) else None,
                veg.get("rap_bare_ground_trend") if veg is not None and rp and usable(rp.mode) else None,
                source=friendly_provider("rap", rp.mode if rp else None, demo), as_of=str(int(rap_year)) if rap_year is not None else None,
            ),
        ]
        herd_info = herd.get(pid, {})
        occ = occupancy_signal(herd_info.get("days_in"), herd_info.get("days_rested"))
        if occ is not None:
            signals.append(occ)
        status = combine(signals)
        out_pastures.append({
            "id": pid,
            "name": str(record.get("name") or pid),
            "acres": _num(record.get("acres"), 1),
            "center": [round(float(record["centroid_lon"]), 6), round(float(record["centroid_lat"]), 6)],
            "outline": _ring(record["geometry"]),
            **status.to_dict(),
            "terrain": terrain_by_pasture.get(pid),
        })

    order = {"act": 0, "watch": 1, "unknown": 2, "good": 3}
    out_pastures.sort(key=lambda p: (order.get(p["status"], 9), p["name"]))
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo": bool(demo),
        "ranch": {
            "name": app_settings.ranch.name,
            "address": app_settings.ranch.address,
            "center": [round(lon, 6), round(lat, 6)],
            "acres": _num(pastures["acres"].sum(), 1),
            "timezone": app_settings.ranch.timezone,
        },
        "sources": sources,
        "weather": weather,
        "alerts": alerts,
        "fire": fire,
        "rain": rain or None,
        "pastures": out_pastures,
        "counts": {k: sum(1 for p in out_pastures if p["status"] == k) for k in ("act", "watch", "good", "unknown")},
    }
