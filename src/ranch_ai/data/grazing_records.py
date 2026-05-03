from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_grazing_records(
    pastures: pd.DataFrame,
    weather_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic stocking and rest cycles for each pasture."""
    rng = np.random.default_rng(seed + 31)
    records: list[dict[str, object]] = []

    weather_lookup = weather_df.sort_values(["pasture_id", "week_start"]).copy()

    for pasture_idx, pasture in pastures.reset_index(drop=True).iterrows():
        pasture_weather = weather_lookup.loc[weather_lookup["pasture_id"] == pasture["pasture_id"]]
        graze_weeks = int(rng.integers(2, 5))
        rest_weeks = int(rng.integers(2, 6))
        cycle_length = graze_weeks + rest_weeks
        cycle_phase = int(rng.integers(0, cycle_length))
        base_animal_units = pasture["acres"] / rng.uniform(17, 24)

        for week_index, row in enumerate(pasture_weather.itertuples(index=False)):
            in_graze_cycle = ((week_index + cycle_phase) % cycle_length) < graze_weeks
            rainfall_stress = max(0.0, 18 - row.rainfall_7d)
            temperature_factor = 1 + max(0.0, row.temp_max_7d - 34) / 100
            animal_units_present = 0.0
            supplement_kg = 0.0

            if in_graze_cycle:
                animal_units_present = max(0.0, base_animal_units * rng.uniform(0.88, 1.16) * temperature_factor)
                supplement_kg = max(0.0, animal_units_present * max(0.0, rainfall_stress * 0.28))

            records.append(
                {
                    "pasture_id": pasture["pasture_id"],
                    "week_start": row.week_start,
                    "animal_units_present": round(animal_units_present, 2),
                    "supplement_kg": round(supplement_kg, 2),
                    "grazed_this_week": bool(in_graze_cycle),
                }
            )

    return pd.DataFrame(records)

