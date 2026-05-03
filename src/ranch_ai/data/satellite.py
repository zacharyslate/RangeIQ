from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_satellite(
    pastures: pd.DataFrame,
    weather_df: pd.DataFrame,
    soil_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic NDVI and EVI values tied to weekly weather and soil capacity."""
    rng = np.random.default_rng(seed + 23)
    merged = weather_df.merge(soil_df[["pasture_id", "soil_water_capacity"]], on="pasture_id", how="left")

    ndvi_baseline = []
    ndvi_mean = []
    evi_mean = []

    for row in merged.itertuples(index=False):
        week_of_year = int(pd.Timestamp(row.week_start).isocalendar().week)
        seasonal_greenup = 0.38 + 0.12 * np.sin(((week_of_year - 9) / 52) * 2 * np.pi)
        soil_bonus = (row.soil_water_capacity - 120) / 850
        rainfall_bonus = row.rainfall_7d / 180
        baseline = np.clip(seasonal_greenup + soil_bonus, 0.18, 0.72)
        observed = np.clip(baseline + rainfall_bonus + rng.normal(0, 0.025), 0.12, 0.84)
        evi = np.clip(observed * 0.82 + 0.05 + rng.normal(0, 0.02), 0.10, 0.72)

        ndvi_baseline.append(round(float(baseline), 3))
        ndvi_mean.append(round(float(observed), 3))
        evi_mean.append(round(float(evi), 3))

    return pd.DataFrame(
        {
            "pasture_id": merged["pasture_id"],
            "week_start": merged["week_start"],
            "ndvi_mean": ndvi_mean,
            "ndvi_historical_mean": ndvi_baseline,
            "evi_mean": evi_mean,
        }
    )


def _monthly_drought_category(rainfall_deficit_mm: float, ndvi_anomaly: float) -> str:
    severity = rainfall_deficit_mm + max(0.0, -ndvi_anomaly * 200)
    if severity >= 48:
        return "D4"
    if severity >= 38:
        return "D3"
    if severity >= 28:
        return "D2"
    if severity >= 18:
        return "D1"
    if severity >= 10:
        return "D0"
    return "None"


def generate_synthetic_vegetation_history(
    pastures: pd.DataFrame,
    soil_df: pd.DataFrame,
    years: int = 10,
    seed: int = 42,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Create a synthetic 5-10 year monthly vegetation and rainfall history."""
    rng = np.random.default_rng(seed + 101)
    month_anchor = pd.Timestamp(end_date or pd.Timestamp.today()).to_period("M").to_timestamp()
    month_index = pd.date_range(end=month_anchor, periods=years * 12, freq="MS")
    soil_lookup = soil_df.set_index("pasture_id")
    records: list[dict[str, object]] = []

    for pasture_idx, pasture in pastures.reset_index(drop=True).iterrows():
        soil_row = soil_lookup.loc[pasture["pasture_id"]]
        for month_position, month_start in enumerate(month_index):
            month_number = month_start.month
            year_number = month_start.year
            seasonal_greenup = 0.34 + 0.14 * np.sin(((month_number - 3) / 12) * 2 * np.pi)
            baseline_rainfall = 18 + 14 * np.sin(((month_number - 2) / 12) * 2 * np.pi)
            interannual_signal = 0.035 * np.sin((year_number - month_index[0].year + pasture_idx) / 1.8)
            drought_pulse = -0.05 if month_number in {6, 7, 8, 9} and (year_number + pasture_idx) % 4 == 0 else 0.0
            soil_bonus = (soil_row["soil_water_capacity"] - 120) / 900

            ndvi_baseline = np.clip(seasonal_greenup + interannual_signal + soil_bonus, 0.16, 0.74)
            rainfall_baseline = max(5.0, baseline_rainfall + (soil_row["soil_productivity_index"] - 55) * 0.25)
            rainfall_mm = max(
                0.0,
                rainfall_baseline
                + 8 * np.sin((month_position + pasture_idx) / 4.0)
                + rng.normal(0, 5.5)
                + drought_pulse * 120,
            )
            ndvi_mean = np.clip(
                ndvi_baseline
                + (rainfall_mm - rainfall_baseline) / 180
                + drought_pulse
                + rng.normal(0, 0.02),
                0.1,
                0.86,
            )
            evi_mean = np.clip(ndvi_mean * 0.8 + 0.06 + rng.normal(0, 0.015), 0.08, 0.72)
            ndvi_anomaly = ndvi_mean - ndvi_baseline
            rainfall_deficit_mm = max(0.0, rainfall_baseline - rainfall_mm)

            records.append(
                {
                    "pasture_id": pasture["pasture_id"],
                    "name": pasture["name"],
                    "month_start": month_start,
                    "ndvi_mean": round(float(ndvi_mean), 3),
                    "ndvi_baseline": round(float(ndvi_baseline), 3),
                    "ndvi_anomaly": round(float(ndvi_anomaly), 3),
                    "evi_mean": round(float(evi_mean), 3),
                    "rainfall_mm": round(float(rainfall_mm), 1),
                    "rainfall_baseline_mm": round(float(rainfall_baseline), 1),
                    "rainfall_deficit_mm": round(float(rainfall_deficit_mm), 1),
                    "drought_category": _monthly_drought_category(float(rainfall_deficit_mm), float(ndvi_anomaly)),
                }
            )

    return pd.DataFrame(records).sort_values(["pasture_id", "month_start"]).reset_index(drop=True)
