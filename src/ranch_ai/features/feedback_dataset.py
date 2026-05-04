from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.models.ranch_domain import LivestockGroup, ManagementUnit, RanchProfile, UnitFeedbackLabel


FEEDBACK_DATASET_COLUMNS = [
    "label_id",
    "observed_on",
    "unit_id",
    "unit_name",
    "unit_type",
    "unit_acres",
    "label_type",
    "label_value",
    "confidence",
    "ranch_type",
    "management_style",
    "rotates_animals",
    "preferred_unit_term",
    "livestock_species",
    "primary_goals",
    "assigned_group_ids",
    "assigned_group_names",
    "assigned_livestock",
    "notes",
]

CALIBRATION_LABEL_MAP: dict[str, dict[str, Any]] = {
    "forage / vegetation condition": {
        "target_family": "forage_condition_score",
        "target_type": "regression",
        "value_map": {"strong": 85.0, "stable": 72.0, "watch": 58.0, "stressed": 42.0, "poor": 24.0},
    },
    "grazing / browsing pressure": {
        "target_family": "grazing_pressure_class",
        "target_type": "classification",
        "value_map": {"light": "LOW", "moderate": "MODERATE", "heavy": "HIGH", "recovering": "RECOVERING"},
    },
    "move / turnout readiness": {
        "target_family": "move_readiness_class",
        "target_type": "classification",
        "value_map": {"ready now": "READY", "hold": "HOLD", "rest longer": "REST", "monitor closely": "WATCH"},
    },
    "ground impact / bare ground": {
        "target_family": "ground_impact_risk_score",
        "target_type": "regression",
        "value_map": {"acceptable": 22.0, "watch": 48.0, "high impact": 78.0, "recovering": 36.0},
    },
    "water access": {
        "target_family": "water_access_risk_score",
        "target_type": "regression",
        "value_map": {"adequate": 18.0, "watch": 46.0, "problem": 82.0},
    },
    "restoration progress": {
        "target_family": "restoration_progress_class",
        "target_type": "classification",
        "value_map": {"improving": "IMPROVING", "stable": "STABLE", "slipping": "SLIPPING"},
    },
    "general observation": {
        "target_family": "general_observation_class",
        "target_type": "classification",
        "value_map": {"positive": "POSITIVE", "mixed": "MIXED", "negative": "NEGATIVE"},
    },
}

CONFIDENCE_WEIGHT_MAP = {"low": 0.5, "medium": 0.75, "high": 1.0}


def build_feedback_dataset(
    labels: dict[str, UnitFeedbackLabel],
    units: list[ManagementUnit],
    profile: RanchProfile,
    livestock_groups: dict[str, LivestockGroup] | None = None,
) -> pd.DataFrame:
    livestock_groups = livestock_groups or {}
    unit_lookup = {unit.unit_id: unit for unit in units}
    rows: list[dict[str, Any]] = []

    for label in labels.values():
        unit = unit_lookup.get(label.unit_id)
        assigned_group_ids = list(unit.assigned_group_ids) if unit is not None else []
        assigned_group_names = [
            livestock_groups[group_id].group_name
            for group_id in assigned_group_ids
            if group_id in livestock_groups
        ]
        rows.append(
            {
                "label_id": label.label_id,
                "observed_on": label.observed_on,
                "unit_id": label.unit_id,
                "unit_name": unit.name if unit is not None else label.unit_id,
                "unit_type": unit.unit_type if unit is not None else "",
                "unit_acres": float(unit.acres) if unit is not None else None,
                "label_type": label.label_type,
                "label_value": label.label_value,
                "confidence": str(label.confidence or "medium").strip().lower() or "medium",
                "ranch_type": profile.ranch_type,
                "management_style": profile.management_style,
                "rotates_animals": bool(profile.rotates_animals),
                "preferred_unit_term": profile.preferred_unit_term,
                "livestock_species": ", ".join(profile.livestock_species),
                "primary_goals": ", ".join(profile.primary_goals),
                "assigned_group_ids": ", ".join(assigned_group_ids),
                "assigned_group_names": ", ".join(assigned_group_names),
                "assigned_livestock": ", ".join(unit.assigned_livestock) if unit is not None else "",
                "notes": label.notes,
            }
        )

    frame = pd.DataFrame(rows, columns=FEEDBACK_DATASET_COLUMNS)
    if frame.empty:
        return frame

    frame["observed_on"] = pd.to_datetime(frame["observed_on"], errors="coerce")
    frame["unit_acres"] = pd.to_numeric(frame["unit_acres"], errors="coerce")
    frame = frame.sort_values(["observed_on", "unit_name", "label_type"], ascending=[False, True, True]).reset_index(drop=True)
    return frame


def summarize_feedback_dataset(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "units_labeled": 0,
            "latest_observation": None,
            "label_types": {},
            "confidence_counts": {},
            "ready_for_model_review": False,
        }

    observed = pd.to_datetime(frame["observed_on"], errors="coerce")
    latest_observation = observed.max()
    return {
        "rows": int(len(frame)),
        "units_labeled": int(frame["unit_id"].nunique()),
        "latest_observation": latest_observation.date().isoformat() if not pd.isna(latest_observation) else None,
        "label_types": {str(key): int(value) for key, value in frame["label_type"].value_counts().items()},
        "confidence_counts": {str(key): int(value) for key, value in frame["confidence"].value_counts().items()},
        "ready_for_model_review": bool(len(frame) >= 5 and frame["unit_id"].nunique() >= 2),
    }


def build_feedback_calibration_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "label_id",
                "observed_on",
                "unit_id",
                "unit_name",
                "label_type",
                "label_value",
                "target_family",
                "target_type",
                "candidate_numeric_target",
                "candidate_class_target",
                "confidence",
                "confidence_weight",
                "management_style",
                "ranch_type",
                "notes",
            ]
        )

    for row in frame.to_dict(orient="records"):
        mapping = CALIBRATION_LABEL_MAP.get(str(row.get("label_type", "")))
        if mapping is None:
            continue
        label_value = str(row.get("label_value", "")).strip().lower()
        mapped_target = mapping["value_map"].get(label_value)
        confidence = str(row.get("confidence", "medium")).strip().lower() or "medium"
        rows.append(
            {
                "label_id": row.get("label_id"),
                "observed_on": row.get("observed_on"),
                "unit_id": row.get("unit_id"),
                "unit_name": row.get("unit_name"),
                "label_type": row.get("label_type"),
                "label_value": row.get("label_value"),
                "target_family": mapping["target_family"],
                "target_type": mapping["target_type"],
                "candidate_numeric_target": float(mapped_target) if mapping["target_type"] == "regression" else None,
                "candidate_class_target": mapped_target if mapping["target_type"] == "classification" else "",
                "confidence": confidence,
                "confidence_weight": CONFIDENCE_WEIGHT_MAP.get(confidence, 0.75),
                "management_style": row.get("management_style"),
                "ranch_type": row.get("ranch_type"),
                "notes": row.get("notes", ""),
            }
        )

    calibration_frame = pd.DataFrame(rows)
    if calibration_frame.empty:
        return calibration_frame

    calibration_frame["observed_on"] = pd.to_datetime(calibration_frame["observed_on"], errors="coerce")
    return calibration_frame.sort_values(
        ["observed_on", "target_family", "unit_name"], ascending=[False, True, True]
    ).reset_index(drop=True)


def summarize_feedback_calibration_dataset(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "target_families": {},
            "regression_targets": 0,
            "classification_targets": 0,
            "weighted_signal": 0.0,
            "ready_for_shadow_review": False,
        }

    regression_count = int((frame["target_type"] == "regression").sum())
    classification_count = int((frame["target_type"] == "classification").sum())
    return {
        "rows": int(len(frame)),
        "target_families": {str(key): int(value) for key, value in frame["target_family"].value_counts().items()},
        "regression_targets": regression_count,
        "classification_targets": classification_count,
        "weighted_signal": round(float(pd.to_numeric(frame["confidence_weight"], errors="coerce").fillna(0).sum()), 2),
        "ready_for_shadow_review": bool(len(frame) >= 8 and frame["target_family"].nunique() >= 2),
    }


def _derive_move_readiness(recommendation: str) -> str:
    value = str(recommendation or "").upper()
    if value == "GRAZE":
        return "READY"
    if value == "REST":
        return "REST"
    if value == "SUPPLEMENT":
        return "WATCH"
    if value in {"REDUCE STOCKING", "DESTOCK WARNING"}:
        return "HOLD"
    return ""


def _derive_grazing_pressure_class(value: Any) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return ""
    if float(numeric) < 0.08:
        return "LIGHT"
    if float(numeric) < 0.18:
        return "MODERATE"
    return "HEAVY"


def _derive_restoration_progress(row: pd.Series) -> str:
    vegetation_status = str(row.get("vegetation_status", "")).strip().lower()
    condition_score = pd.to_numeric(row.get("pasture_condition_score"), errors="coerce")
    if "above" in vegetation_status or (not pd.isna(condition_score) and float(condition_score) >= 72):
        return "IMPROVING"
    if "below" in vegetation_status or (not pd.isna(condition_score) and float(condition_score) < 48):
        return "SLIPPING"
    return "STABLE"


def _derive_general_observation(row: pd.Series) -> str:
    condition_score = pd.to_numeric(row.get("pasture_condition_score"), errors="coerce")
    attention_level = str(row.get("attention_level", "")).strip().lower()
    if (not pd.isna(condition_score) and float(condition_score) >= 72) or attention_level == "low":
        return "POSITIVE"
    if (not pd.isna(condition_score) and float(condition_score) < 48) or attention_level == "high":
        return "NEGATIVE"
    return "MIXED"


def build_feedback_shadow_review_dataset(calibration_frame: pd.DataFrame, latest_snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "label_id",
        "observed_on",
        "unit_id",
        "unit_name",
        "target_family",
        "target_type",
        "candidate_numeric_target",
        "candidate_class_target",
        "live_signal_source",
        "live_numeric_signal",
        "live_class_signal",
        "delta",
        "absolute_error",
        "class_match",
        "confidence",
        "confidence_weight",
        "management_style",
        "ranch_type",
        "notes",
    ]
    if calibration_frame.empty or latest_snapshot.empty:
        return pd.DataFrame(columns=columns)

    latest = latest_snapshot.copy()
    if "pasture_id" not in latest.columns:
        return pd.DataFrame(columns=columns)
    latest_lookup = latest.drop_duplicates(subset=["pasture_id"]).set_index("pasture_id", drop=False)

    rows: list[dict[str, Any]] = []
    for item in calibration_frame.to_dict(orient="records"):
        unit_id = str(item.get("unit_id", "")).strip()
        if not unit_id or unit_id not in latest_lookup.index:
            continue
        snapshot_row = latest_lookup.loc[unit_id]
        target_family = str(item.get("target_family", ""))
        target_type = str(item.get("target_type", ""))
        live_signal_source = ""
        live_numeric_signal: float | None = None
        live_class_signal = ""

        if target_family == "forage_condition_score":
            live_signal_source = "pasture_condition_score"
            value = pd.to_numeric(snapshot_row.get("pasture_condition_score"), errors="coerce")
            live_numeric_signal = None if pd.isna(value) else float(value)
        elif target_family == "ground_impact_risk_score":
            live_signal_source = "stocking_risk_score"
            value = pd.to_numeric(snapshot_row.get("stocking_risk_score"), errors="coerce")
            live_numeric_signal = None if pd.isna(value) else float(value)
        elif target_family == "water_access_risk_score":
            live_signal_source = "water_risk_score"
            value = pd.to_numeric(snapshot_row.get("water_risk_score"), errors="coerce")
            live_numeric_signal = None if pd.isna(value) else float(value)
        elif target_family == "grazing_pressure_class":
            live_signal_source = "grazing_pressure"
            live_class_signal = _derive_grazing_pressure_class(snapshot_row.get("grazing_pressure"))
        elif target_family == "move_readiness_class":
            live_signal_source = "recommendation"
            live_class_signal = _derive_move_readiness(snapshot_row.get("recommendation"))
        elif target_family == "restoration_progress_class":
            live_signal_source = "vegetation_status + pasture_condition_score"
            live_class_signal = _derive_restoration_progress(snapshot_row)
        elif target_family == "general_observation_class":
            live_signal_source = "pasture_condition_score + attention_level"
            live_class_signal = _derive_general_observation(snapshot_row)

        candidate_numeric = pd.to_numeric(item.get("candidate_numeric_target"), errors="coerce")
        delta = None
        absolute_error = None
        class_match = None
        if target_type == "regression" and live_numeric_signal is not None and not pd.isna(candidate_numeric):
            delta = round(float(live_numeric_signal) - float(candidate_numeric), 2)
            absolute_error = round(abs(delta), 2)
        elif target_type == "classification" and live_class_signal:
            class_match = str(live_class_signal).upper() == str(item.get("candidate_class_target", "")).upper()

        rows.append(
            {
                "label_id": item.get("label_id"),
                "observed_on": item.get("observed_on"),
                "unit_id": unit_id,
                "unit_name": item.get("unit_name") or snapshot_row.get("name") or unit_id,
                "target_family": target_family,
                "target_type": target_type,
                "candidate_numeric_target": None if pd.isna(candidate_numeric) else float(candidate_numeric),
                "candidate_class_target": item.get("candidate_class_target", ""),
                "live_signal_source": live_signal_source,
                "live_numeric_signal": live_numeric_signal,
                "live_class_signal": live_class_signal,
                "delta": delta,
                "absolute_error": absolute_error,
                "class_match": class_match,
                "confidence": item.get("confidence"),
                "confidence_weight": item.get("confidence_weight"),
                "management_style": item.get("management_style"),
                "ranch_type": item.get("ranch_type"),
                "notes": item.get("notes", ""),
            }
        )

    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    frame["observed_on"] = pd.to_datetime(frame["observed_on"], errors="coerce")
    return frame.sort_values(["observed_on", "target_family", "unit_name"], ascending=[False, True, True]).reset_index(drop=True)


def summarize_feedback_shadow_review_dataset(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "comparable_rows": 0,
            "regression_rows": 0,
            "classification_rows": 0,
            "mean_absolute_error": None,
            "classification_match_rate": None,
            "overall_alignment_rate": None,
        }

    regression = frame.loc[frame["absolute_error"].notna()].copy()
    classification = frame.loc[frame["class_match"].notna()].copy()
    comparable_rows = int(len(regression) + len(classification))
    mae = None if regression.empty else round(float(pd.to_numeric(regression["absolute_error"], errors="coerce").mean()), 2)
    class_match_rate = None if classification.empty else round(float(classification["class_match"].astype(float).mean()), 3)

    aligned_regression = 0
    if not regression.empty:
        aligned_regression = int((pd.to_numeric(regression["absolute_error"], errors="coerce") <= 12.0).sum())
    aligned_classification = int(classification["class_match"].sum()) if not classification.empty else 0
    overall_alignment_rate = None
    if comparable_rows > 0:
        overall_alignment_rate = round(float((aligned_regression + aligned_classification) / comparable_rows), 3)

    return {
        "rows": int(len(frame)),
        "comparable_rows": comparable_rows,
        "regression_rows": int(len(regression)),
        "classification_rows": int(len(classification)),
        "mean_absolute_error": mae,
        "classification_match_rate": class_match_rate,
        "overall_alignment_rate": overall_alignment_rate,
    }
