import warnings

import pandas as pd

from ranch_ai.models.forage_model import predict_forage_scores, train_forage_model
from ranch_ai.models.stress_model import train_stress_model
from ranch_ai.pipeline import build_synthetic_dataset


def test_models_drop_all_missing_public_features_without_imputer_warning():
    _, weekly_data, _, _ = build_synthetic_dataset(weeks=12, seed=42)
    model_df = weekly_data.copy()
    model_df["public_range_prod_index"] = pd.NA

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        forage_artifacts = train_forage_model(model_df, random_state=42)
        model_df["predicted_forage_score"] = predict_forage_scores(forage_artifacts, model_df)
        stress_artifacts = train_stress_model(model_df, random_state=42)

    warning_messages = [str(item.message) for item in captured]
    assert "public_range_prod_index" not in forage_artifacts.feature_columns
    assert "public_range_prod_index" not in stress_artifacts.feature_columns
    assert not any("Skipping features without any observed values" in message for message in warning_messages)
