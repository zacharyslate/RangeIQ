from __future__ import annotations

import pandas as pd


DROUGHT_THRESHOLDS = [
    (75, "None", 0),
    (55, "D0", 1),
    (40, "D1", 2),
    (28, "D2", 3),
    (18, "D3", 4),
    (-1, "D4", 5),
]


def _classify_drought(rainfall_30d: float) -> tuple[str, int]:
    for minimum_rain, category, score in DROUGHT_THRESHOLDS:
        if rainfall_30d >= minimum_rain:
            return category, score
    return "D4", 5


def generate_synthetic_drought(weather_df: pd.DataFrame) -> pd.DataFrame:
    """Infer weekly drought categories from rolling rainfall deficits."""
    drought_df = weather_df.sort_values(["pasture_id", "week_start"]).copy()
    drought_df["rainfall_30d_proxy"] = (
        drought_df.groupby("pasture_id")["rainfall_7d"]
        .transform(lambda series: series.rolling(window=4, min_periods=1).sum())
        .round(2)
    )
    drought_df["temp_penalty"] = (drought_df["temp_max_7d"] - 34).clip(lower=0) * 1.5
    drought_df["drought_basis"] = drought_df["rainfall_30d_proxy"] - drought_df["temp_penalty"]

    categories = drought_df["drought_basis"].apply(_classify_drought)
    drought_df["drought_category"] = categories.str[0]
    drought_df["drought_numeric"] = categories.str[1].astype(int)

    return drought_df[["pasture_id", "week_start", "drought_category", "drought_numeric"]]

