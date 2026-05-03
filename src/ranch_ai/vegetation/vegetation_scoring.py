from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ranch_ai.vegetation.vegetation_types import TrendLabel, VegetationScore


def calculate_trend_label(
    values: pd.Series | list[float] | np.ndarray,
    *,
    threshold_ratio: float = 0.02,
    minimum_points: int = 3,
) -> tuple[TrendLabel, float | None]:
    series = pd.Series(values, dtype="float64").dropna()
    if len(series) < minimum_points:
        return "unknown", None

    x = np.arange(len(series), dtype=float)
    slope = float(np.polyfit(x, series.to_numpy(dtype=float), 1)[0])
    scale = max(float(series.abs().mean()), 1.0)
    normalized_slope = slope / scale

    if normalized_slope > threshold_ratio:
        return "increasing", round(normalized_slope, 4)
    if normalized_slope < -threshold_ratio:
        return "declining", round(normalized_slope, 4)
    return "stable", round(normalized_slope, 4)


def ndvi_status_label(anomaly_percent: float | None) -> str:
    if anomaly_percent is None or pd.isna(anomaly_percent):
        return "Unknown"
    if anomaly_percent > 10:
        return "Above normal"
    if anomaly_percent < -10:
        return "Below normal"
    return "Normal"


def trend_score_value(label: TrendLabel) -> float | None:
    if label == "increasing":
        return 1.0
    if label == "stable":
        return 0.0
    if label == "declining":
        return -1.0
    return None


def calculate_vegetation_health_score(
    *,
    ndvi_latest: float | None,
    ndvi_historical_mean: float | None,
    ndvi_anomaly: float | None,
    ndvi_anomaly_percent: float | None = None,
    perennial_grass_trend: TrendLabel,
    bare_ground_trend: TrendLabel,
    shrub_trend: TrendLabel,
    production_trend: TrendLabel,
    rap_cover_series: pd.DataFrame,
    rap_production_series: pd.DataFrame,
) -> VegetationScore:
    score = 100.0
    drivers: list[str] = []
    positives: list[str] = []
    cautions: list[str] = []

    if ndvi_anomaly_percent is not None and not pd.isna(ndvi_anomaly_percent):
        if ndvi_anomaly_percent > 15:
            score += 8
            positives.append("NDVI is well above normal for this time of year")
        elif ndvi_anomaly_percent > 10:
            score += 4
            positives.append("Greenness is a little above normal")
        elif ndvi_anomaly_percent < -20:
            score -= 14
            cautions.append("Greenness is well below normal for this time of year")
        elif ndvi_anomaly_percent < -10:
            score -= 8
            cautions.append("Greenness is slipping below normal")
    elif ndvi_anomaly is not None and not pd.isna(ndvi_anomaly):
        if ndvi_anomaly >= 0.10:
            score += 4
        elif ndvi_anomaly <= -0.10:
            score -= 6

    if perennial_grass_trend == "increasing":
        score += 8
        positives.append("Perennial grass cover is improving")
    elif perennial_grass_trend == "stable":
        score += 2
    elif perennial_grass_trend == "declining":
        score -= 12
        cautions.append("Perennial grass cover is declining")

    if bare_ground_trend == "declining":
        score += 6
        positives.append("Bare ground is easing")
    elif bare_ground_trend == "increasing":
        score -= 15
        cautions.append("Bare ground is increasing")

    if shrub_trend == "declining":
        score += 3
    elif shrub_trend == "increasing":
        score -= 8
        cautions.append("Shrub cover is increasing")

    if production_trend == "increasing":
        score += 7
        positives.append("Rangeland production is improving")
    elif production_trend == "stable":
        score += 1
    elif production_trend == "declining":
        score -= 10
        cautions.append("Rangeland production is below its long-term pattern")

    if not rap_cover_series.empty:
        latest_cover = rap_cover_series.sort_values("year").iloc[-1]
        perennial_cover = pd.to_numeric(latest_cover.get("rap_perennial_grass_forb_cover_pct"), errors="coerce")
        bare_ground = pd.to_numeric(latest_cover.get("rap_bare_ground_pct"), errors="coerce")
        if pd.notna(perennial_cover) and float(perennial_cover) < 20:
            score -= 6
            cautions.append("Perennial grass cover is on the lean side")
        if pd.notna(bare_ground) and float(bare_ground) > 30:
            score -= 6
            cautions.append("Bare ground is still high")

    if not rap_production_series.empty:
        production_values = pd.to_numeric(rap_production_series["rap_total_herbaceous_production_lb_ac"], errors="coerce").dropna()
        if len(production_values) >= 3:
            latest = float(production_values.iloc[-1])
            baseline = float(production_values.iloc[:-1].mean()) if len(production_values) > 1 else float(production_values.mean())
            if latest < baseline * 0.9:
                score -= 6
                cautions.append("Production is below the long-term average")
            elif latest > baseline * 1.05:
                score += 3
                positives.append("Production is running above the long-term average")

    if ndvi_latest is None and rap_cover_series.empty and rap_production_series.empty:
        return VegetationScore(
            score=None,
            category="Unknown",
            explanation="RangeIQ could not build a vegetation score because both NDVI and RAP history were unavailable.",
            drivers=[],
        )

    score = max(0.0, min(100.0, score))
    if score >= 85:
        category = "Excellent"
    elif score >= 70:
        category = "Good"
    elif score >= 55:
        category = "Watch"
    elif score >= 40:
        category = "Stressed"
    else:
        category = "Degraded"

    drivers = positives[:2] + cautions[:3]
    if not drivers:
        drivers = ["Vegetation indicators are mixed but mostly stable right now."]

    positive_text = positives[0] if positives else "Current greenness is not sending a strong signal either way."
    caution_text = cautions[0] if cautions else "Long-term rangeland structure looks fairly steady."
    explanation = (
        f"{positive_text}, but {caution_text.lower()}."
        if cautions
        else f"{positive_text} Long-term rangeland structure looks fairly steady."
    )

    return VegetationScore(score=round(score, 1), category=category, explanation=explanation, drivers=drivers)
