from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
import pandas as pd


def _stable_seed(aoi_id: str, seed: int) -> int:
    digest = hashlib.sha1(aoi_id.encode("utf-8")).hexdigest()
    return seed + int(digest[:8], 16)


def generate_mock_ndvi_history(
    aoi_id: str,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    seed: int = 42,
) -> pd.DataFrame:
    index = pd.date_range(start=pd.Timestamp(start_date).normalize(), end=pd.Timestamp(end_date).normalize(), freq="MS")
    rng = np.random.default_rng(_stable_seed(aoi_id, seed))
    rows: list[dict[str, object]] = []

    for idx, timestamp in enumerate(index):
        seasonal = 0.34 + 0.14 * np.sin(((timestamp.month - 4) / 12.0) * 2 * np.pi)
        slow_trend = np.sin(idx / 18.0) * 0.015
        ndvi_mean = np.clip(seasonal + slow_trend + rng.normal(0, 0.025), 0.05, 0.88)
        ndvi_std = np.clip(0.04 + rng.normal(0, 0.008), 0.01, 0.09)
        rows.append(
            {
                "pasture_id": aoi_id,
                "date": pd.Timestamp(timestamp),
                "ndvi_mean": round(float(ndvi_mean), 3),
                "ndvi_min": round(float(max(0.0, ndvi_mean - ndvi_std * 1.6)), 3),
                "ndvi_max": round(float(min(1.0, ndvi_mean + ndvi_std * 1.6)), 3),
                "ndvi_std": round(float(ndvi_std), 3),
                "source": "Mock NDVI history",
            }
        )

    return pd.DataFrame(rows)


def generate_mock_rap_cover_history(
    aoi_id: str,
    start_year: int,
    end_year: int,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(_stable_seed(f"{aoi_id}-rap-cover", seed))
    years = list(range(start_year, end_year + 1))
    rows: list[dict[str, object]] = []
    perennial = rng.uniform(24, 38)
    bare_ground = rng.uniform(14, 28)
    shrub = rng.uniform(7, 18)
    annual = rng.uniform(8, 18)
    tree = rng.uniform(0, 4)
    litter = rng.uniform(7, 14)

    for year in years:
        wet_cycle = np.sin((year - years[0]) / 2.4) * 2.2
        perennial = np.clip(perennial + wet_cycle * 0.15 + rng.normal(0, 1.2), 12, 55)
        shrub = np.clip(shrub + rng.normal(0.08, 0.45), 2, 28)
        tree = np.clip(tree + rng.normal(0.02, 0.12), 0, 8)
        annual = np.clip(annual + rng.normal(0.0, 1.1), 2, 30)
        bare_ground = np.clip(bare_ground + rng.normal(0.12, 0.9) - wet_cycle * 0.08, 6, 45)
        litter = np.clip(litter + rng.normal(0.02, 0.55), 3, 22)
        total_cover = np.clip(annual + perennial + shrub + tree + litter, 30, 94)
        rows.append(
            {
                "pasture_id": aoi_id,
                "year": int(year),
                "rap_annual_grass_forb_cover_pct": round(float(annual), 3),
                "rap_perennial_grass_forb_cover_pct": round(float(perennial), 3),
                "rap_shrub_cover_pct": round(float(shrub), 3),
                "rap_tree_cover_pct": round(float(tree), 3),
                "rap_litter_cover_pct": round(float(litter), 3),
                "rap_bare_ground_pct": round(float(bare_ground), 3),
                "rap_total_vegetation_cover_pct": round(float(total_cover), 3),
                "rap_annual_temp_f": round(float(rng.uniform(54, 69)), 2),
                "rap_annual_precip_in": round(float(rng.uniform(7.5, 18.0)), 2),
                "source": "Mock RAP cover history",
            }
        )

    return pd.DataFrame(rows)


def generate_mock_rap_production_history(
    aoi_id: str,
    start_year: int,
    end_year: int,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(_stable_seed(f"{aoi_id}-rap-production", seed))
    cover_df = generate_mock_rap_cover_history(aoi_id, start_year, end_year, seed=seed + 7)
    rows: list[dict[str, object]] = []

    for record in cover_df.itertuples(index=False):
        perennial = float(record.rap_perennial_grass_forb_cover_pct)
        annual = float(record.rap_annual_grass_forb_cover_pct)
        herbaceous = np.clip(perennial * 18 + annual * 10 + rng.normal(0, 55), 140, 1500)
        rows.append(
            {
                "pasture_id": aoi_id,
                "year": int(record.year),
                "rap_annual_production_lb_ac": round(float(annual * 9 + rng.normal(0, 20)), 3),
                "rap_perennial_production_lb_ac": round(float(perennial * 16 + rng.normal(0, 30)), 3),
                "rap_total_herbaceous_production_lb_ac": round(float(herbaceous), 3),
                "source": "Mock RAP production history",
            }
        )

    return pd.DataFrame(rows)


def generate_mock_rap_production_16day_history(
    aoi_id: str,
    start_year: int,
    end_year: int,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(_stable_seed(f"{aoi_id}-rap-16day", seed))
    rows: list[dict[str, object]] = []

    for year in range(start_year, end_year + 1):
        doy_values = [16 + idx * 16 for idx in range(23)]
        peak = rng.integers(128, 208)
        seasonal_max = rng.uniform(35, 110)
        for doy in doy_values:
            date = pd.Timestamp(year=year, month=1, day=1) + pd.to_timedelta(doy - 1, unit="D")
            pulse = np.exp(-((doy - peak) ** 2) / 2600.0)
            perennial = max(0.0, pulse * seasonal_max + rng.normal(0, 3.5))
            annual = max(0.0, pulse * seasonal_max * rng.uniform(0.15, 0.45) + rng.normal(0, 2.5))
            herbaceous = perennial + annual
            rows.append(
                {
                    "pasture_id": aoi_id,
                    "date": date,
                    "year": year,
                    "doy": doy,
                    "rap_annual_production_16day_lb_ac": round(float(annual), 3),
                    "rap_perennial_production_16day_lb_ac": round(float(perennial), 3),
                    "rap_total_herbaceous_16day_lb_ac": round(float(herbaceous), 3),
                    "source": "Mock RAP 16-day production history",
                }
            )

    return pd.DataFrame(rows)


@dataclass
class MockVegetationProvider:
    seed: int = 42
    provider_name: str = "mock"

    def get_ndvi_history(self, aoi_id: str, start_date: str | pd.Timestamp, end_date: str | pd.Timestamp) -> pd.DataFrame:
        return generate_mock_ndvi_history(aoi_id, start_date, end_date, seed=self.seed)

    def get_rap_cover_history(self, aoi_id: str, start_year: int, end_year: int) -> pd.DataFrame:
        return generate_mock_rap_cover_history(aoi_id, start_year, end_year, seed=self.seed)

    def get_rap_production_history(self, aoi_id: str, start_year: int, end_year: int) -> pd.DataFrame:
        return generate_mock_rap_production_history(aoi_id, start_year, end_year, seed=self.seed)

    def get_rap_production_16day_history(self, aoi_id: str, start_year: int, end_year: int) -> pd.DataFrame:
        return generate_mock_rap_production_16day_history(aoi_id, start_year, end_year, seed=self.seed)
