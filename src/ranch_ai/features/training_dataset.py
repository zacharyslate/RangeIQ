from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.models.public_data_schema import PublicDataBundle, TrainingDatasetArtifacts


def _aggregate_public_weather_weekly(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=["week_start"])

    history = history_df.copy()
    history["date"] = pd.to_datetime(history["date"])
    history["week_start"] = history["date"] - pd.to_timedelta(history["date"].dt.weekday, unit="D")
    weekly = (
        history.groupby("week_start", as_index=False)
        .agg(
            public_temp_mean_7d_f=("public_temp_mean_f", "mean"),
            public_temp_max_7d_f=("public_temp_max_f", "max"),
            public_temp_min_7d_f=("public_temp_min_f", "min"),
            public_precip_7d_in=("public_precip_in", "sum"),
            public_humidity_7d_pct=("public_humidity_pct", "mean"),
            public_wind_speed_7d_mph=("public_wind_speed_mph", "mean"),
        )
        .round(3)
    )
    return weekly


def build_training_dataset(
    weekly_df: pd.DataFrame,
    public_bundle: PublicDataBundle,
    app_settings: Settings = settings,
) -> TrainingDatasetArtifacts:
    dataset = weekly_df.copy()
    dataset["week_start"] = pd.to_datetime(dataset["week_start"])
    dataset["month_start"] = dataset["week_start"].dt.to_period("M").dt.to_timestamp()

    if app_settings.training.use_public_data:
        public_weather_weekly = _aggregate_public_weather_weekly(public_bundle.historical_weather)
        if not public_weather_weekly.empty:
            dataset = dataset.merge(public_weather_weekly, on="week_start", how="left")

        if not public_bundle.soils.empty:
            dataset = dataset.merge(public_bundle.soils.drop(columns=["source"], errors="ignore"), on="pasture_id", how="left")

        if not public_bundle.drought.empty:
            drought = public_bundle.drought.drop(columns=["source"], errors="ignore").copy()
            drought["week_start"] = pd.to_datetime(drought["week_start"])
            dataset = dataset.merge(drought, on="week_start", how="left")

        if not public_bundle.vegetation.empty:
            vegetation = public_bundle.vegetation.drop(columns=["source"], errors="ignore").copy()
            vegetation["month_start"] = pd.to_datetime(vegetation["month_start"])
            dataset = dataset.merge(vegetation, on=["pasture_id", "month_start"], how="left")

    public_columns = [column for column in dataset.columns if column.startswith("public_")]
    summary = {
        "rows": int(len(dataset)),
        "pastures": int(dataset["pasture_id"].nunique()) if "pasture_id" in dataset else 0,
        "weeks": int(dataset["week_start"].nunique()) if "week_start" in dataset else 0,
        "sensor_data_enabled": bool(app_settings.training.use_sensor_data),
        "public_feature_columns": public_columns,
        "public_feature_count": int(len(public_columns)),
        "non_null_public_cells": int(dataset[public_columns].notna().sum().sum()) if public_columns else 0,
        "source_status": [
            {
                **{
                    key: value.isoformat() if isinstance(value, pd.Timestamp) else value
                    for key, value in asdict(status).items()
                },
                "loaded_at": status.loaded_at.isoformat() if status.loaded_at is not None else None,
            }
            for status in public_bundle.source_status
        ],
    }

    return TrainingDatasetArtifacts(dataset=dataset.drop(columns=["month_start"], errors="ignore"), summary=summary)
