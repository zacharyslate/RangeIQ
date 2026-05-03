from __future__ import annotations

import pandas as pd


def build_network_alerts(status_df: pd.DataFrame, network_health_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for row in status_df.itertuples(index=False):
        if row.status != "ONLINE":
            rows.append({"station_id": row.station_id, "severity": "HIGH", "message": f"{row.station_id} is {row.status.lower()}."})
        if row.battery_status != "OK":
            rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_id} battery status is {row.battery_status.lower()}."})
        if row.signal_status != "OK":
            rows.append({"station_id": row.station_id, "severity": "MEDIUM", "message": f"{row.station_id} signal status is {row.signal_status.lower()}."})
    if not network_health_df.empty:
        for row in network_health_df.itertuples(index=False):
            if getattr(row, "station_type", "") == "relay" and getattr(row, "status", "") != "ONLINE":
                rows.append({"station_id": row.station_id, "severity": "HIGH", "message": f"Relay {row.station_id} needs attention."})
    return pd.DataFrame(rows)
