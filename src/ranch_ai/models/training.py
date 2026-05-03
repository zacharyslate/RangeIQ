from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ranch_ai.models.forage_model import predict_forage_scores, train_forage_model
from ranch_ai.models.model_store import WorkspaceModelStore
from ranch_ai.models.stress_model import predict_stress_class, train_stress_model
from ranch_ai.optimization.recommendations import generate_recommendations


@dataclass
class TrainingArtifacts:
    scored_data: pd.DataFrame
    forage_metrics: dict[str, float]
    stress_metrics: dict[str, float | str]
    selected_forage_model: str
    model_storage_summary: dict[str, object]


def apply_ranchiq_scores(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    scored["stocking_risk_score"] = (
        scored["stocking_ratio"] * 38
        + (55 - scored["predicted_forage_score"]).clip(lower=0) * 0.72
        + scored["drought_numeric"] * 8
        + scored["grazing_pressure"] * 110
    ).clip(lower=0, upper=100).round(1)
    scored["pasture_condition_score"] = (
        scored["predicted_forage_score"] * 0.55
        + scored["pasture_recovery_score"] * 0.24
        + scored["soil_productivity_index"] * 0.12
        + scored["ndvi_mean"] * 100 * 0.11
        - scored["water_risk_score"] * 0.14
        - scored["stocking_risk_score"] * 0.08
    ).clip(lower=0, upper=100).round(1)
    scored["condition_band"] = pd.cut(
        scored["pasture_condition_score"],
        bins=[-1, 45, 70, 1000],
        labels=["WATCH", "STABLE", "STRONG"],
    ).astype(str)
    return scored


def train_and_score(
    df: pd.DataFrame,
    random_state: int = 42,
    model_store: WorkspaceModelStore | None = None,
) -> TrainingArtifacts:
    scored = df.copy()

    stored_bundle = model_store.load_matching(scored, random_state=random_state) if model_store is not None else None
    if stored_bundle is not None:
        forage_artifacts = stored_bundle.forage_artifacts
        stress_artifacts = stored_bundle.stress_artifacts
        model_storage_summary = model_store.summary(status="loaded", metadata=stored_bundle.metadata) if model_store is not None else {"status": "loaded"}
    else:
        forage_artifacts = train_forage_model(scored, random_state=random_state)
        stress_artifacts = train_stress_model(scored.assign(predicted_forage_score=predict_forage_scores(forage_artifacts, scored)), random_state=random_state)
        model_storage_summary = {"enabled": False, "status": "trained"}
        if model_store is not None:
            metadata = model_store.save(
                scored,
                random_state=random_state,
                forage_artifacts=forage_artifacts,
                stress_artifacts=stress_artifacts,
            )
            model_storage_summary = model_store.summary(status="trained", metadata=metadata)

    scored["predicted_forage_score"] = predict_forage_scores(forage_artifacts, scored)
    scored["predicted_stress_class"] = predict_stress_class(stress_artifacts, scored)
    scored = apply_ranchiq_scores(scored)

    recommendation_df = generate_recommendations(scored)
    scored["recommendation"] = recommendation_df["recommendation"]
    scored["recommendation_reason"] = recommendation_df["recommendation_reason"]

    return TrainingArtifacts(
        scored_data=scored,
        forage_metrics=forage_artifacts.metrics,
        stress_metrics=stress_artifacts.metrics,
        selected_forage_model=forage_artifacts.selected_model_name,
        model_storage_summary=model_storage_summary,
    )
