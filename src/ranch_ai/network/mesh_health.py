from __future__ import annotations

import pandas as pd


def calculate_last_seen_per_node(raw_packets_df: pd.DataFrame) -> pd.DataFrame:
    if raw_packets_df.empty:
        return pd.DataFrame(columns=["station_id", "last_seen"])
    grouped = raw_packets_df.groupby("from_node", as_index=False)["received_at"].max()
    return grouped.rename(columns={"from_node": "station_id", "received_at": "last_seen"})


def calculate_packet_count_per_node(raw_packets_df: pd.DataFrame) -> pd.DataFrame:
    if raw_packets_df.empty:
        return pd.DataFrame(columns=["station_id", "packet_count"])
    grouped = raw_packets_df.groupby("from_node", as_index=False).size()
    return grouped.rename(columns={"from_node": "station_id", "size": "packet_count"})


def calculate_average_signal_per_node(raw_packets_df: pd.DataFrame) -> pd.DataFrame:
    if raw_packets_df.empty:
        return pd.DataFrame(columns=["station_id", "avg_rssi", "avg_snr"])
    grouped = raw_packets_df.groupby("from_node", as_index=False)[["rssi", "snr"]].mean()
    return grouped.rename(columns={"from_node": "station_id", "rssi": "avg_rssi", "snr": "avg_snr"})


def identify_offline_nodes(status_df: pd.DataFrame) -> list[str]:
    if status_df.empty:
        return []
    return status_df.loc[status_df["status"] != "ONLINE", "station_id"].astype(str).tolist()


def identify_low_signal_nodes(network_health_df: pd.DataFrame, low_signal_rssi: float) -> list[str]:
    if network_health_df.empty:
        return []
    return network_health_df.loc[network_health_df["avg_rssi"] < low_signal_rssi, "station_id"].astype(str).tolist()


def identify_relay_nodes(stations_df: pd.DataFrame) -> list[str]:
    if stations_df.empty or "station_type" not in stations_df.columns:
        return []
    return stations_df.loc[stations_df["station_type"] == "relay", "station_id"].astype(str).tolist()


def build_node_health_table(
    raw_packets_df: pd.DataFrame,
    status_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    low_signal_rssi: float = -115,
) -> pd.DataFrame:
    health = calculate_last_seen_per_node(raw_packets_df)
    counts = calculate_packet_count_per_node(raw_packets_df)
    signal = calculate_average_signal_per_node(raw_packets_df)

    merged = stations_df.copy()
    merged = merged.merge(health, on="station_id", how="left")
    merged = merged.merge(counts, on="station_id", how="left")
    merged = merged.merge(signal, on="station_id", how="left")
    merged = merged.merge(status_df[["station_id", "status", "battery_status", "signal_status", "sensor_error_status", "alerts"]], on="station_id", how="left")
    if "packet_count" in merged.columns:
        merged["packet_count"] = merged["packet_count"].fillna(0).astype(int)
    merged["low_signal_flag"] = merged["avg_rssi"].fillna(0) < low_signal_rssi
    return merged.sort_values(["station_type", "station_id"]).reset_index(drop=True)


def summarize_mesh_health(
    raw_packets_df: pd.DataFrame,
    status_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    low_signal_rssi: float = -115,
) -> dict[str, object]:
    network_health_df = build_node_health_table(raw_packets_df, status_df, stations_df, low_signal_rssi=low_signal_rssi)
    return {
        "total_nodes": int(len(stations_df)),
        "offline_nodes": identify_offline_nodes(status_df),
        "low_signal_nodes": identify_low_signal_nodes(network_health_df, low_signal_rssi=low_signal_rssi),
        "relay_nodes": identify_relay_nodes(stations_df),
        "packet_count": int(raw_packets_df.shape[0]),
        "average_rssi": None if raw_packets_df.empty else round(float(raw_packets_df["rssi"].dropna().mean()), 2),
        "average_snr": None if raw_packets_df.empty else round(float(raw_packets_df["snr"].dropna().mean()), 2),
        "channel_health_summary": "Mock telemetry channel is flowing." if not raw_packets_df.empty else "No packets received.",
    }
