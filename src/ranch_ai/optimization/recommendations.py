from __future__ import annotations

import pandas as pd


RECOMMENDATION_COLORS = {
    "GRAZE": [60, 140, 90, 180],
    "REST": [80, 118, 170, 180],
    "SUPPLEMENT": [201, 151, 51, 180],
    "REDUCE STOCKING": [212, 102, 47, 180],
    "DESTOCK WARNING": [176, 48, 48, 190],
}


def _recommend_row(row: pd.Series) -> tuple[str, str]:
    if (
        row["drought_category"] in {"D3", "D4"}
        or row["water_risk_score"] >= 86
        or (row["risk_score"] >= 84 and row["predicted_forage_score"] < 35)
    ):
        return "DESTOCK WARNING", "Water stress, drought pressure, and weak forage suggest a destocking warning."

    if row["drought_category"] in {"D2", "D3"} or row["stocking_risk_score"] >= 68 or (
        row["grazing_pressure"] >= 0.13 and row["predicted_forage_score"] < 45
    ):
        return "REDUCE STOCKING", "Estimated stocking pressure is too high for current forage and drought conditions."

    if (
        row["predicted_forage_score"] < 48
        or row["ndvi_anomaly"] < -0.05
        or row["soil_moisture_30cm"] < 14
        or row["rainfall_30d"] < 32
        or row["water_risk_score"] >= 55
    ):
        return "SUPPLEMENT", "Forage supply and water-related stress support supplemental feeding."

    if row["animal_units_present"] > 0 and row["predicted_forage_score"] >= 70 and row["risk_score"] < 35 and row["water_risk_score"] < 45:
        return "GRAZE", "The pasture is supporting active grazing with strong forage and low stress."

    if row["animal_units_present"] <= 0 and (row["days_since_grazed"] < 21 or row["pasture_recovery_score"] < 52):
        return "REST", "The pasture needs more recovery time before another grazing pass."

    return "GRAZE", "Forage, recovery, and moisture indicators support continued grazing."


def generate_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    recommendations = df.apply(_recommend_row, axis=1)
    return pd.DataFrame(
        {
            "recommendation": recommendations.str[0],
            "recommendation_reason": recommendations.str[1],
        },
        index=df.index,
    )
