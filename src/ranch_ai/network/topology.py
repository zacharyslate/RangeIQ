from __future__ import annotations

import pandas as pd


def build_topology_table(stations_df: pd.DataFrame) -> pd.DataFrame:
    if stations_df.empty:
        return pd.DataFrame(columns=["station_id", "station_name", "station_type", "pasture_id"])
    return stations_df[["station_id", "station_name", "station_type", "pasture_id"]].copy()
