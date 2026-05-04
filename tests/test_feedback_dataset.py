import pandas as pd

from ranch_ai.features.feedback_dataset import (
    build_feedback_calibration_dataset,
    build_feedback_dataset,
    build_feedback_shadow_review_dataset,
    summarize_feedback_shadow_review_dataset,
    summarize_feedback_calibration_dataset,
    summarize_feedback_dataset,
)
from ranch_ai.models.ranch_domain import LivestockGroup, RanchProfile, UnitFeedbackLabel, build_management_units


def test_build_feedback_dataset_includes_unit_and_profile_context():
    units = build_management_units(
        pd.DataFrame(
            [
                {
                    "pasture_id": "P-001",
                    "name": "North Pasture",
                    "acres": 120.0,
                    "centroid_lat": 32.1,
                    "centroid_lon": -99.4,
                    "geometry": [[[-99.4, 32.1], [-99.39, 32.1], [-99.39, 32.11], [-99.4, 32.1]]][0],
                    "pasture_condition_score": 58.0,
                    "drought_category": "D1",
                    "grazing_pressure": 0.42,
                    "water_risk_score": 35.0,
                    "stocking_risk_score": 41.0,
                    "recommendation": "REST",
                    "notes": "Source notes",
                }
            ]
        ),
        pd.DataFrame(
            [
                {
                    "pasture_id": "P-001",
                    "ndvi_status": "Below normal",
                    "ndvi_anomaly_percent": -12.5,
                }
            ]
        ),
        RanchProfile(
            ranch_type="horse property",
            management_style="horse turnout",
            livestock_species=["horses"],
            primary_goals=["manage horse turnout"],
            preferred_unit_term="turnout",
        ),
        livestock_groups={
            "mares": LivestockGroup(
                group_id="mares",
                group_name="Broodmares",
                species="horses",
                animal_count=8,
                assigned_unit_id="P-001",
            )
        },
    )
    labels = {
        "feedback-1": UnitFeedbackLabel(
            label_id="feedback-1",
            unit_id="P-001",
            label_type="ground impact / bare ground",
            label_value="watch",
            observed_on="2026-05-05",
            confidence="high",
            notes="Hoof impact concentrated near the gate.",
        )
    }

    frame = build_feedback_dataset(
        labels,
        units,
        RanchProfile(
            ranch_type="horse property",
            management_style="horse turnout",
            livestock_species=["horses"],
            primary_goals=["manage horse turnout"],
            preferred_unit_term="turnout",
        ),
        {"mares": LivestockGroup(group_id="mares", group_name="Broodmares", species="horses", animal_count=8, assigned_unit_id="P-001")},
    )

    assert frame.loc[0, "unit_name"] == "North Pasture"
    assert frame.loc[0, "label_type"] == "ground impact / bare ground"
    assert frame.loc[0, "confidence"] == "high"
    assert frame.loc[0, "management_style"] == "horse turnout"


def test_summarize_feedback_dataset_reports_model_review_readiness():
    frame = pd.DataFrame(
        [
            {
                "label_id": f"feedback-{idx}",
                "observed_on": f"2026-05-0{idx + 1}",
                "unit_id": "P-001" if idx < 3 else "P-002",
                "unit_name": "North" if idx < 3 else "South",
                "unit_type": "pasture",
                "unit_acres": 100.0,
                "label_type": "forage / vegetation condition",
                "label_value": "watch",
                "confidence": "high" if idx % 2 == 0 else "medium",
                "ranch_type": "rotational cattle ranch",
                "management_style": "rotational grazing",
                "rotates_animals": True,
                "preferred_unit_term": "pasture",
                "livestock_species": "cattle",
                "primary_goals": "monitor forage condition",
                "assigned_group_ids": "",
                "assigned_group_names": "",
                "assigned_livestock": "",
                "notes": "",
            }
            for idx in range(5)
        ]
    )

    summary = summarize_feedback_dataset(frame)

    assert summary["rows"] == 5
    assert summary["units_labeled"] == 2
    assert summary["ready_for_model_review"] is True
    assert summary["label_types"]["forage / vegetation condition"] == 5


def test_build_feedback_calibration_dataset_maps_labels_to_targets():
    feedback_frame = pd.DataFrame(
        [
            {
                "label_id": "feedback-1",
                "observed_on": "2026-05-05",
                "unit_id": "P-001",
                "unit_name": "North Pasture",
                "unit_type": "pasture",
                "unit_acres": 120.0,
                "label_type": "forage / vegetation condition",
                "label_value": "stressed",
                "confidence": "high",
                "ranch_type": "rotational cattle ranch",
                "management_style": "rotational grazing",
                "rotates_animals": True,
                "preferred_unit_term": "pasture",
                "livestock_species": "cattle",
                "primary_goals": "monitor forage condition",
                "assigned_group_ids": "",
                "assigned_group_names": "",
                "assigned_livestock": "",
                "notes": "Dry spell stress.",
            },
            {
                "label_id": "feedback-2",
                "observed_on": "2026-05-06",
                "unit_id": "P-001",
                "unit_name": "North Pasture",
                "unit_type": "pasture",
                "unit_acres": 120.0,
                "label_type": "move / turnout readiness",
                "label_value": "hold",
                "confidence": "medium",
                "ranch_type": "rotational cattle ranch",
                "management_style": "rotational grazing",
                "rotates_animals": True,
                "preferred_unit_term": "pasture",
                "livestock_species": "cattle",
                "primary_goals": "monitor forage condition",
                "assigned_group_ids": "",
                "assigned_group_names": "",
                "assigned_livestock": "",
                "notes": "Not ready yet.",
            },
        ]
    )

    calibration = build_feedback_calibration_dataset(feedback_frame)

    forage_row = calibration.loc[calibration["label_id"] == "feedback-1"].iloc[0]
    readiness_row = calibration.loc[calibration["label_id"] == "feedback-2"].iloc[0]

    assert forage_row["target_family"] == "forage_condition_score"
    assert forage_row["target_type"] == "regression"
    assert forage_row["candidate_numeric_target"] == 42.0
    assert readiness_row["target_family"] == "move_readiness_class"
    assert readiness_row["target_type"] == "classification"
    assert readiness_row["candidate_class_target"] == "HOLD"


def test_summarize_feedback_calibration_dataset_reports_shadow_review_readiness():
    calibration_frame = pd.DataFrame(
        [
            {
                "label_id": f"feedback-{idx}",
                "observed_on": f"2026-05-{idx + 1:02d}",
                "unit_id": "P-001" if idx < 4 else "P-002",
                "unit_name": "North" if idx < 4 else "South",
                "label_type": "forage / vegetation condition" if idx < 4 else "move / turnout readiness",
                "label_value": "watch",
                "target_family": "forage_condition_score" if idx < 4 else "move_readiness_class",
                "target_type": "regression" if idx < 4 else "classification",
                "candidate_numeric_target": 58.0 if idx < 4 else None,
                "candidate_class_target": "" if idx < 4 else "WATCH",
                "confidence": "high" if idx % 2 == 0 else "medium",
                "confidence_weight": 1.0 if idx % 2 == 0 else 0.75,
                "management_style": "rotational grazing",
                "ranch_type": "rotational cattle ranch",
                "notes": "",
            }
            for idx in range(8)
        ]
    )

    summary = summarize_feedback_calibration_dataset(calibration_frame)

    assert summary["rows"] == 8
    assert summary["regression_targets"] == 4
    assert summary["classification_targets"] == 4
    assert summary["ready_for_shadow_review"] is True


def test_build_feedback_shadow_review_dataset_compares_live_outputs():
    calibration = pd.DataFrame(
        [
            {
                "label_id": "feedback-1",
                "observed_on": "2026-05-05",
                "unit_id": "P-001",
                "unit_name": "North Pasture",
                "label_type": "forage / vegetation condition",
                "label_value": "stressed",
                "target_family": "forage_condition_score",
                "target_type": "regression",
                "candidate_numeric_target": 42.0,
                "candidate_class_target": "",
                "confidence": "high",
                "confidence_weight": 1.0,
                "management_style": "rotational grazing",
                "ranch_type": "rotational cattle ranch",
                "notes": "",
            },
            {
                "label_id": "feedback-2",
                "observed_on": "2026-05-06",
                "unit_id": "P-001",
                "unit_name": "North Pasture",
                "label_type": "move / turnout readiness",
                "label_value": "hold",
                "target_family": "move_readiness_class",
                "target_type": "classification",
                "candidate_numeric_target": None,
                "candidate_class_target": "HOLD",
                "confidence": "medium",
                "confidence_weight": 0.75,
                "management_style": "rotational grazing",
                "ranch_type": "rotational cattle ranch",
                "notes": "",
            },
        ]
    )
    latest_snapshot = pd.DataFrame(
        [
            {
                "pasture_id": "P-001",
                "name": "North Pasture",
                "pasture_condition_score": 54.0,
                "stocking_risk_score": 61.0,
                "water_risk_score": 47.0,
                "grazing_pressure": 0.21,
                "recommendation": "REDUCE STOCKING",
                "vegetation_status": "Below normal",
                "attention_level": "High",
            }
        ]
    )

    review = build_feedback_shadow_review_dataset(calibration, latest_snapshot)

    forage_row = review.loc[review["label_id"] == "feedback-1"].iloc[0]
    move_row = review.loc[review["label_id"] == "feedback-2"].iloc[0]

    assert forage_row["live_signal_source"] == "pasture_condition_score"
    assert forage_row["live_numeric_signal"] == 54.0
    assert forage_row["absolute_error"] == 12.0
    assert move_row["live_signal_source"] == "recommendation"
    assert move_row["live_class_signal"] == "HOLD"
    assert move_row["class_match"] is True


def test_summarize_feedback_shadow_review_dataset_reports_alignment():
    review = pd.DataFrame(
        [
            {
                "label_id": "feedback-1",
                "absolute_error": 8.0,
                "class_match": None,
            },
            {
                "label_id": "feedback-2",
                "absolute_error": 16.0,
                "class_match": None,
            },
            {
                "label_id": "feedback-3",
                "absolute_error": None,
                "class_match": True,
            },
            {
                "label_id": "feedback-4",
                "absolute_error": None,
                "class_match": False,
            },
        ]
    )

    summary = summarize_feedback_shadow_review_dataset(review)

    assert summary["rows"] == 4
    assert summary["regression_rows"] == 2
    assert summary["classification_rows"] == 2
    assert summary["mean_absolute_error"] == 12.0
    assert summary["classification_match_rate"] == 0.5
    assert summary["overall_alignment_rate"] == 0.5
