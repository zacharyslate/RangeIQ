from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.data.drought import generate_synthetic_drought
from ranch_ai.data.grazing_records import generate_synthetic_grazing_records
from ranch_ai.data.satellite import generate_synthetic_satellite, generate_synthetic_vegetation_history
from ranch_ai.data.sensors import aggregate_weekly_sensor_features, generate_synthetic_sensor_readings, save_sensor_schema
from ranch_ai.features.training_dataset import build_training_dataset
from ranch_ai.data.soil import generate_synthetic_soil_profiles
from ranch_ai.data.weather import build_week_index, generate_synthetic_weather
from ranch_ai.features.engineering import build_weekly_table, engineer_pasture_features
from ranch_ai.models.public_data_schema import PublicDataBundle
from ranch_ai.models.training import TrainingArtifacts, train_and_score
from ranch_ai.reports.monthly_report import MonthlyReportArtifacts, build_monthly_ranch_report
from ranch_ai.services.public_data_service import PublicDataService
from ranch_ai.utils.io import load_pastures, save_dataframe, save_text


@dataclass
class MvpArtifacts:
    pastures: pd.DataFrame
    weekly_data: pd.DataFrame
    scored_data: pd.DataFrame
    latest_snapshot: pd.DataFrame
    vegetation_history: pd.DataFrame
    monthly_report_table: pd.DataFrame
    monthly_report_markdown: str
    sensor_readings: pd.DataFrame
    model_metrics: dict[str, dict[str, float | str]]
    selected_forage_model: str
    public_data_bundle: PublicDataBundle
    training_dataset_summary: dict[str, object]


def build_synthetic_dataset(
    pasture_path: str | Path | None = None,
    geojson_text: str | None = None,
    uploaded_boundary_name: str | None = None,
    uploaded_boundary_bytes: bytes | None = None,
    weeks: int | None = None,
    history_years: int | None = None,
    seed: int | None = None,
    app_settings: Settings = settings,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    active_weeks = weeks or app_settings.default_weeks
    active_history_years = history_years or app_settings.default_history_years
    active_seed = seed or app_settings.random_seed

    pastures = load_pastures(
        path=pasture_path,
        geojson_text=geojson_text,
        uploaded_name=uploaded_boundary_name,
        uploaded_bytes=uploaded_boundary_bytes,
    )
    week_index = build_week_index(active_weeks)
    soil_df = generate_synthetic_soil_profiles(pastures, seed=active_seed)
    weather_df = generate_synthetic_weather(pastures, week_index, seed=active_seed)
    satellite_df = generate_synthetic_satellite(pastures, weather_df, soil_df, seed=active_seed)
    drought_df = generate_synthetic_drought(weather_df)
    grazing_df = generate_synthetic_grazing_records(pastures, weather_df, seed=active_seed)
    sensor_df = generate_synthetic_sensor_readings(pastures, weather_df, soil_df, seed=active_seed)
    vegetation_history_df = generate_synthetic_vegetation_history(
        pastures,
        soil_df,
        years=active_history_years,
        seed=active_seed,
    )
    weekly_sensor_df = aggregate_weekly_sensor_features(sensor_df)

    weekly_data = build_weekly_table(
        pastures=pastures,
        weather_df=weather_df,
        satellite_df=satellite_df,
        soil_df=soil_df,
        drought_df=drought_df,
        grazing_df=grazing_df,
        sensor_weekly_df=weekly_sensor_df,
    )
    weekly_data = engineer_pasture_features(weekly_data, seed=active_seed)
    return pastures, weekly_data, sensor_df, vegetation_history_df


def run_mvp_pipeline(
    pasture_path: str | Path | None = None,
    geojson_text: str | None = None,
    uploaded_boundary_name: str | None = None,
    uploaded_boundary_bytes: bytes | None = None,
    weeks: int | None = None,
    history_years: int | None = None,
    seed: int | None = None,
    write_outputs: bool = True,
    app_settings: Settings = settings,
) -> MvpArtifacts:
    pastures, weekly_data, sensor_df, vegetation_history_df = build_synthetic_dataset(
        pasture_path=pasture_path,
        geojson_text=geojson_text,
        uploaded_boundary_name=uploaded_boundary_name,
        uploaded_boundary_bytes=uploaded_boundary_bytes,
        weeks=weeks,
        history_years=history_years,
        seed=seed,
        app_settings=app_settings,
    )
    public_data_bundle = PublicDataService(app_settings).load_public_data_bundle(
        pastures=pastures,
        start_date=weekly_data["week_start"].min(),
        end_date=weekly_data["week_start"].max(),
        history_years=history_years,
    )
    training_dataset_artifacts = build_training_dataset(weekly_data, public_data_bundle, app_settings=app_settings)
    weekly_data = training_dataset_artifacts.dataset

    training_artifacts: TrainingArtifacts = train_and_score(weekly_data, random_state=seed or app_settings.random_seed)

    scored_data = training_artifacts.scored_data.sort_values(["pasture_id", "week_start"]).reset_index(drop=True)
    latest_week = scored_data["week_start"].max()
    latest_snapshot = (
        scored_data.loc[scored_data["week_start"] == latest_week]
        .sort_values(["risk_score", "predicted_forage_score"], ascending=[False, True])
        .reset_index(drop=True)
    )
    monthly_report_artifacts: MonthlyReportArtifacts = build_monthly_ranch_report(
        latest_snapshot=latest_snapshot,
        ranch_name=app_settings.default_ranch_name,
        ranch_address=app_settings.default_ranch_address,
    )

    if write_outputs:
        vegetation_export = (
            public_data_bundle.vegetation_artifacts.ndvi_series
            if public_data_bundle.vegetation_artifacts is not None and not public_data_bundle.vegetation_artifacts.ndvi_series.empty
            else vegetation_history_df
        )
        save_dataframe(weekly_data, app_settings.default_weekly_output_path)
        save_dataframe(scored_data, app_settings.default_scored_output_path)
        save_dataframe(vegetation_export, app_settings.default_history_output_path)
        save_dataframe(monthly_report_artifacts.report_table, app_settings.default_monthly_report_csv_path)
        save_text(monthly_report_artifacts.markdown, app_settings.default_monthly_report_md_path)
        save_sensor_schema(sensor_df, app_settings.default_sensor_output_path)

    return MvpArtifacts(
        pastures=pastures,
        weekly_data=weekly_data,
        scored_data=scored_data,
        latest_snapshot=latest_snapshot,
        vegetation_history=vegetation_history_df,
        monthly_report_table=monthly_report_artifacts.report_table,
        monthly_report_markdown=monthly_report_artifacts.markdown,
        sensor_readings=sensor_df,
        model_metrics={
            "forage_model": training_artifacts.forage_metrics,
            "stress_model": training_artifacts.stress_metrics,
        },
        selected_forage_model=training_artifacts.selected_forage_model,
        public_data_bundle=public_data_bundle,
        training_dataset_summary=training_dataset_artifacts.summary,
    )
