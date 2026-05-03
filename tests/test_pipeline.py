import copy

from ranch_ai.config import settings
from ranch_ai.pipeline import run_mvp_pipeline


def test_pipeline_produces_required_columns():
    artifacts = run_mvp_pipeline(weeks=12, seed=42, write_outputs=False)
    required_columns = {
        "pasture_id",
        "week_start",
        "rainfall_7d",
        "rainfall_30d",
        "rainfall_90d",
        "ndvi_mean",
        "ndvi_anomaly",
        "soil_type",
        "soil_water_capacity",
        "days_since_grazed",
        "animal_units_present",
        "grazing_pressure",
        "rainfall_deficit_30d",
        "water_risk_score",
        "stocking_risk_score",
        "pasture_condition_score",
        "manual_forage_score",
        "predicted_forage_score",
        "risk_score",
        "recommendation",
    }

    assert required_columns.issubset(set(artifacts.scored_data.columns))
    assert len(artifacts.latest_snapshot) == artifacts.pastures["pasture_id"].nunique()
    assert not artifacts.scored_data.empty
    assert not artifacts.vegetation_history.empty
    assert not artifacts.monthly_report_table.empty
    assert "RangeIQ Monthly Report" in artifacts.monthly_report_markdown
    assert len(artifacts.public_data_bundle.source_status) == 5
    assert artifacts.public_data_bundle.vegetation_artifacts is not None
    assert artifacts.training_dataset_summary["sensor_data_enabled"] is False
    assert artifacts.training_dataset_summary["public_feature_count"] > 0
    assert artifacts.sensor_readings.empty
    assert artifacts.model_storage_summary["status"] in {"trained", "loaded"}


def test_pipeline_recommendations_are_valid():
    artifacts = run_mvp_pipeline(weeks=10, history_years=5, seed=7, write_outputs=False)
    valid_recommendations = {
        "GRAZE",
        "REST",
        "SUPPLEMENT",
        "REDUCE STOCKING",
        "DESTOCK WARNING",
    }
    assert set(artifacts.latest_snapshot["recommendation"]).issubset(valid_recommendations)
    assert artifacts.vegetation_history["month_start"].nunique() == 60


def test_pipeline_persists_models_per_workspace(tmp_path):
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.workspace_user_data_root = tmp_path / "workspaces"

    first_run = run_mvp_pipeline(
        weeks=12,
        seed=42,
        write_outputs=False,
        app_settings=runtime_settings,
        workspace_id="user-demo-models",
    )
    model_dir = runtime_settings.workspace_model_dir_for("user-demo-models")

    assert first_run.model_storage_summary["status"] == "trained"
    assert (model_dir / "metadata.json").exists()
    assert (model_dir / "forage_model.pkl").exists()
    assert (model_dir / "stress_model.pkl").exists()

    second_run = run_mvp_pipeline(
        weeks=12,
        seed=42,
        write_outputs=False,
        app_settings=runtime_settings,
        workspace_id="user-demo-models",
    )

    assert second_run.model_storage_summary["status"] == "loaded"
    assert second_run.selected_forage_model == first_run.selected_forage_model
