from __future__ import annotations

import numpy as np
import pandas as pd


DROUGHT_TO_SCORE = {"None": 0, "D0": 1, "D1": 2, "D2": 3, "D3": 4, "D4": 5}


def build_weekly_table(
    pastures: pd.DataFrame,
    weather_df: pd.DataFrame,
    satellite_df: pd.DataFrame,
    soil_df: pd.DataFrame,
    drought_df: pd.DataFrame,
    grazing_df: pd.DataFrame,
    sensor_weekly_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge source tables into one pasture-week modeling table."""
    pasture_columns = [
        "pasture_id",
        "name",
        "acres",
        "geometry",
        "centroid_lon",
        "centroid_lat",
        "boundary_status",
        "source_address",
        "notes",
    ]
    pasture_columns = [column for column in pasture_columns if column in pastures.columns]
    merged = (
        weather_df.merge(satellite_df, on=["pasture_id", "week_start"], how="left")
        .merge(drought_df, on=["pasture_id", "week_start"], how="left")
        .merge(grazing_df, on=["pasture_id", "week_start"], how="left")
        .merge(soil_df, on="pasture_id", how="left")
        .merge(pastures[pasture_columns], on="pasture_id", how="left")
    )

    if sensor_weekly_df is not None and not sensor_weekly_df.empty:
        merged = merged.merge(sensor_weekly_df, on=["pasture_id", "week_start"], how="left")

    return merged.sort_values(["pasture_id", "week_start"]).reset_index(drop=True)


def compute_rainfall_rolling_sums(df: pd.DataFrame) -> pd.DataFrame:
    rainfall_df = df.copy()
    rainfall_df["rainfall_30d"] = (
        rainfall_df.groupby("pasture_id")["rainfall_7d"]
        .transform(lambda series: series.rolling(window=4, min_periods=1).sum())
        .round(2)
    )
    rainfall_df["rainfall_90d"] = (
        rainfall_df.groupby("pasture_id")["rainfall_7d"]
        .transform(lambda series: series.rolling(window=13, min_periods=1).sum())
        .round(2)
    )
    return rainfall_df


def compute_ndvi_anomaly(df: pd.DataFrame) -> pd.Series:
    return (df["ndvi_mean"] - df["ndvi_historical_mean"]).round(3)


def compute_grazing_pressure(df: pd.DataFrame) -> pd.Series:
    pressure = df["animal_units_present"] / df["acres"].replace(0, np.nan)
    return pressure.fillna(0).round(3)


def compute_days_since_grazed(df: pd.DataFrame) -> pd.Series:
    result = []
    for _, pasture_df in df.groupby("pasture_id", sort=False):
        last_grazed: pd.Timestamp | None = None
        for row in pasture_df.itertuples(index=False):
            week_start = pd.Timestamp(row.week_start)
            grazed_this_week = bool(row.grazed_this_week)
            if grazed_this_week:
                result.append(0)
                last_grazed = week_start
                continue

            if last_grazed is None:
                result.append(56)
            else:
                result.append(int((week_start - last_grazed).days))
    return pd.Series(result, index=df.index, dtype="int64")


def compute_heat_stress_index(df: pd.DataFrame) -> pd.Series:
    heat_excess = (df["temp_max_7d"] - 32).clip(lower=0)
    index = 0.45 * df["temp_avg_7d"] + 0.55 * df["temp_max_7d"] + heat_excess
    return index.round(2)


def compute_pasture_recovery_score(df: pd.DataFrame) -> pd.Series:
    score = (
        28
        + df["rainfall_30d"] * 0.22
        + df["days_since_grazed"] * 0.42
        + df["ndvi_mean"] * 28
        + df["soil_water_capacity"] * 0.09
        - df["grazing_pressure"] * 170
        - df["drought_numeric"] * 7
    )
    return score.clip(lower=0, upper=100).round(1)


def compute_drought_risk_score(df: pd.DataFrame) -> pd.Series:
    ndvi_penalty = (-df["ndvi_anomaly"]).clip(lower=0) * 150
    rainfall_penalty = (55 - df["rainfall_30d"]).clip(lower=0) * 0.85
    heat_penalty = (df["heat_stress_index"] - 30).clip(lower=0) * 1.25
    soil_relief = df["soil_water_capacity"] * 0.06 + df["soil_moisture_30cm"].fillna(0) * 0.7

    risk = 8 + df["drought_numeric"] * 11 + ndvi_penalty + rainfall_penalty + heat_penalty + df["grazing_pressure"] * 185
    risk = risk - soil_relief
    return risk.clip(lower=0, upper=100).round(1)


def compute_rainfall_deficit_30d(df: pd.DataFrame) -> pd.Series:
    return (55 - df["rainfall_30d"]).clip(lower=0).round(1)


def compute_estimated_carrying_capacity_au(df: pd.DataFrame) -> pd.Series:
    carrying_capacity = (
        df["acres"] * 0.035
        + df["ndvi_mean"] * df["acres"] * 0.032
        + df["soil_productivity_index"] * 0.045
        + df["rainfall_90d"] * 0.018
        - df["drought_numeric"] * 1.8
    )
    return carrying_capacity.clip(lower=2.0).round(1)


def compute_water_risk_score(df: pd.DataFrame) -> pd.Series:
    water_stress = (
        df["rainfall_deficit_30d"] * 1.1
        + (18 - df["soil_moisture_30cm"]).clip(lower=0) * 2.4
        + df["drought_numeric"] * 10
        + (df["temp_max_7d"] - 34).clip(lower=0) * 1.6
    )
    return water_stress.clip(lower=0, upper=100).round(1)


def engineer_pasture_features(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Create the full synthetic feature set and a training target."""
    rng = np.random.default_rng(seed + 59)
    engineered = df.sort_values(["pasture_id", "week_start"]).copy()
    engineered["drought_numeric"] = engineered["drought_category"].map(DROUGHT_TO_SCORE).fillna(0).astype(int)

    engineered = compute_rainfall_rolling_sums(engineered)
    engineered["ndvi_anomaly"] = compute_ndvi_anomaly(engineered)
    engineered["grazing_pressure"] = compute_grazing_pressure(engineered)
    engineered["days_since_grazed"] = compute_days_since_grazed(engineered)
    engineered["heat_stress_index"] = compute_heat_stress_index(engineered)
    engineered["soil_moisture_30cm"] = engineered.get("soil_moisture_30cm", pd.Series(index=engineered.index)).fillna(
        engineered["soil_water_capacity"] * 0.12
    )
    engineered["pasture_recovery_score"] = compute_pasture_recovery_score(engineered)
    engineered["risk_score"] = compute_drought_risk_score(engineered)
    engineered["rainfall_deficit_30d"] = compute_rainfall_deficit_30d(engineered)
    engineered["estimated_carrying_capacity_au"] = compute_estimated_carrying_capacity_au(engineered)
    engineered["stocking_ratio"] = (
        engineered["animal_units_present"] / engineered["estimated_carrying_capacity_au"].replace(0, np.nan)
    ).fillna(0).round(2)
    engineered["water_risk_score"] = compute_water_risk_score(engineered)

    forage_signal = (
        42
        + engineered["rainfall_30d"] * 0.18
        + engineered["ndvi_mean"] * 26
        + engineered["evi_mean"] * 18
        + engineered["soil_water_capacity"] * 0.06
        + engineered["days_since_grazed"] * 0.08
        + engineered["soil_moisture_30cm"] * 0.6
        - engineered["drought_numeric"] * 7
        - engineered["grazing_pressure"] * 140
        - (engineered["temp_max_7d"] - 32).clip(lower=0) * 1.4
        + rng.normal(0, 3.5, size=len(engineered))
    )
    engineered["manual_forage_score"] = forage_signal.clip(lower=0, upper=100).round(1)
    engineered["stress_class"] = pd.cut(
        engineered["risk_score"],
        bins=[-1, 35, 65, 1000],
        labels=["LOW", "MODERATE", "HIGH"],
    ).astype(str)
    engineered["pasture_condition_baseline"] = (
        engineered["manual_forage_score"] * 0.52
        + engineered["pasture_recovery_score"] * 0.26
        + engineered["ndvi_mean"] * 100 * 0.16
        - engineered["water_risk_score"] * 0.12
    ).clip(lower=0, upper=100).round(1)

    return engineered
