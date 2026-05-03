from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


NUMERIC_FEATURES = [
    "rainfall_7d",
    "rainfall_30d",
    "rainfall_90d",
    "temp_avg_7d",
    "temp_max_7d",
    "ndvi_mean",
    "ndvi_anomaly",
    "evi_mean",
    "soil_water_capacity",
    "days_since_grazed",
    "animal_units_present",
    "grazing_pressure",
    "supplement_kg",
    "soil_moisture_30cm",
    "heat_stress_index",
    "pasture_recovery_score",
    "risk_score",
    "public_temp_mean_7d_f",
    "public_temp_max_7d_f",
    "public_precip_7d_in",
    "public_humidity_7d_pct",
    "public_wind_speed_7d_mph",
    "public_usdm_score",
    "public_usdm_drought_coverage_pct",
    "public_usdm_max_intensity_pct",
    "public_available_water_capacity_in",
    "public_range_prod_index",
    "public_ndvi_mean",
    "public_ndvi_historical_mean",
    "public_ndvi_anomaly",
    "public_fractional_cover",
    "public_rap_annual_grass_cover_pct",
    "public_rap_perennial_grass_cover_pct",
    "public_rap_shrub_cover_pct",
    "public_rap_tree_cover_pct",
    "public_rap_bare_ground_pct",
    "public_rap_litter_cover_pct",
    "public_rap_total_vegetation_cover_pct",
    "public_rap_herbaceous_production_lb_ac",
    "public_rap_annual_production_lb_ac",
    "public_rap_perennial_production_lb_ac",
    "public_rap_perennial_trend_score",
    "public_rap_bare_ground_trend_score",
    "public_rap_shrub_trend_score",
    "public_rap_production_trend_score",
]

CATEGORICAL_FEATURES = ["soil_type", "dominant_forage", "drought_category"]


@dataclass
class ForageModelArtifacts:
    model: Pipeline
    selected_model_name: str
    metrics: dict[str, float]
    feature_columns: list[str]


def _resolve_feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric_features = [column for column in NUMERIC_FEATURES if column in df.columns and not df[column].isna().all()]
    categorical_features = [
        column for column in CATEGORICAL_FEATURES if column in df.columns and df[column].notna().any()
    ]
    return numeric_features, categorical_features


def _build_preprocessor(numeric_features: list[str], categorical_features: list[str]) -> ColumnTransformer:
    transformers = []
    if numeric_features:
        transformers.append(("numeric", SimpleImputer(strategy="median"), numeric_features))
    if categorical_features:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encoder", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_features,
            )
        )

    if not transformers:
        raise ValueError("No usable forage-model feature columns were available after dropping all-missing fields.")

    return ColumnTransformer(transformers=transformers)


def train_forage_model(df: pd.DataFrame, random_state: int = 42) -> ForageModelArtifacts:
    numeric_features, categorical_features = _resolve_feature_columns(df)
    feature_columns = numeric_features + categorical_features
    X = df[feature_columns]
    y = df["manual_forage_score"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=random_state)

    candidates = {
        "RandomForestRegressor": RandomForestRegressor(n_estimators=250, random_state=random_state, min_samples_leaf=2),
        "GradientBoostingRegressor": GradientBoostingRegressor(random_state=random_state),
    }

    best_artifacts: ForageModelArtifacts | None = None

    for model_name, estimator in candidates.items():
        pipeline = Pipeline(steps=[("preprocess", _build_preprocessor(numeric_features, categorical_features)), ("model", estimator)])
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        metrics = {
            "mae": round(float(mean_absolute_error(y_test, predictions)), 3),
            "rmse": round(float(sqrt(mean_squared_error(y_test, predictions))), 3),
            "r2": round(float(r2_score(y_test, predictions)), 3),
        }

        artifacts = ForageModelArtifacts(
            model=pipeline,
            selected_model_name=model_name,
            metrics=metrics,
            feature_columns=feature_columns,
        )

        if best_artifacts is None or artifacts.metrics["mae"] < best_artifacts.metrics["mae"]:
            best_artifacts = artifacts

    assert best_artifacts is not None
    return best_artifacts


def predict_forage_scores(artifacts: ForageModelArtifacts, df: pd.DataFrame) -> pd.Series:
    predictions = artifacts.model.predict(df[artifacts.feature_columns])
    return pd.Series(predictions, index=df.index).clip(lower=0, upper=100).round(1)
