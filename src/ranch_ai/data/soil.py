from __future__ import annotations

import numpy as np
import pandas as pd


SOIL_TYPES = [
    "Sandy loam",
    "Clay loam",
    "Gravelly clay",
    "Fine sandy loam",
    "Shallow clay",
]

FORAGE_TYPES = [
    "Native mixed grass",
    "Little bluestem",
    "Sideoats grama",
    "Bermudagrass",
    "Buffalograss",
]

SOIL_LIMITATIONS = [
    "Seasonal droughtiness",
    "Runoff potential",
    "Shallow rooting depth",
    "Variable infiltration",
    "Moderate salinity risk",
]


def generate_synthetic_soil_profiles(pastures: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Create a stable pasture-level soil and forage profile."""
    rng = np.random.default_rng(seed + 11)
    rows: list[dict[str, object]] = []

    for pasture in pastures.itertuples(index=False):
        soil_type = SOIL_TYPES[rng.integers(0, len(SOIL_TYPES))]
        dominant_forage = FORAGE_TYPES[rng.integers(0, len(FORAGE_TYPES))]
        soil_water_capacity = float(np.clip(rng.normal(125, 22), 75, 180))
        soil_productivity_index = float(np.clip(42 + (soil_water_capacity - 75) * 0.42 + rng.normal(0, 4), 35, 92))
        limitation = SOIL_LIMITATIONS[rng.integers(0, len(SOIL_LIMITATIONS))]

        rows.append(
            {
                "pasture_id": pasture.pasture_id,
                "soil_type": soil_type,
                "soil_water_capacity": round(soil_water_capacity, 1),
                "soil_productivity_index": round(soil_productivity_index, 1),
                "soil_limitation": limitation,
                "dominant_forage": dominant_forage,
            }
        )

    return pd.DataFrame(rows)
