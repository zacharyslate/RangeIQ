from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


NUMERIC_FEATURES = [
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
    "predicted_forage_score",
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
class StressModelArtifacts:
    model: Pipeline
    metrics: dict[str, float | str]
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
        raise ValueError("No usable stress-model feature columns were available after dropping all-missing fields.")

    return ColumnTransformer(transformers=transformers)


def train_stress_model(df: pd.DataFrame, random_state: int = 42) -> StressModelArtifacts:
    numeric_features, categorical_features = _resolve_feature_columns(df)
    feature_columns = numeric_features + categorical_features
    X = df[feature_columns]
    y = df["stress_class"]

    pipeline = Pipeline(
        steps=[
            ("preprocess", _build_preprocessor(numeric_features, categorical_features)),
            ("model", RandomForestClassifier(n_estimators=250, random_state=random_state, min_samples_leaf=2)),
        ]
    )

    class_counts = y.value_counts()
    unique_classes = int(y.nunique())
    test_size_count = max(1, int(round(len(df) * 0.25)))
    can_use_holdout = len(df) >= max(8, unique_classes * 2)
    can_stratify = can_use_holdout and not class_counts.empty and int(class_counts.min()) >= 2 and test_size_count >= unique_classes

    if can_use_holdout:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.25,
            random_state=random_state,
            stratify=y if can_stratify else None,
        )
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
    else:
        pipeline.fit(X, y)
        X_test = X
        y_test = y
        predictions = pipeline.predict(X_test)

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predictions)), 3),
        "report": classification_report(y_test, predictions, zero_division=0),
    }
    return StressModelArtifacts(model=pipeline, metrics=metrics, feature_columns=feature_columns)


def predict_stress_class(artifacts: StressModelArtifacts, df: pd.DataFrame) -> pd.Series:
    predictions = artifacts.model.predict(df[artifacts.feature_columns])
    return pd.Series(predictions, index=df.index, dtype="string")
