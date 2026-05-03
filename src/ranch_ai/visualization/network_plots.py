from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_station_status_counts(status_df: pd.DataFrame):
    if status_df.empty:
        return px.bar(pd.DataFrame({"status": [], "count": []}), x="status", y="count", title="Station Status Counts")
    counts = status_df.groupby("status", as_index=False).size().rename(columns={"size": "count"})
    return px.bar(counts, x="status", y="count", color="status", title="Station Status Counts")


def plot_signal_history(raw_packets_df: pd.DataFrame, station_id: str):
    station_df = raw_packets_df.loc[raw_packets_df["from_node"] == station_id].sort_values("received_at")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=station_df["received_at"], y=station_df["rssi"], mode="lines", name="RSSI"))
    figure.add_trace(go.Scatter(x=station_df["received_at"], y=station_df["snr"], mode="lines", name="SNR", yaxis="y2"))
    figure.update_layout(
        title=f"Signal History: {station_id}",
        xaxis_title="Received at",
        yaxis=dict(title="RSSI"),
        yaxis2=dict(title="SNR", overlaying="y", side="right"),
    )
    return figure


def plot_packets_per_station(raw_packets_df: pd.DataFrame):
    if raw_packets_df.empty:
        return px.bar(pd.DataFrame({"station_id": [], "packet_count": []}), x="station_id", y="packet_count", title="Packets per Station")
    counts = raw_packets_df.groupby("from_node", as_index=False).size().rename(columns={"from_node": "station_id", "size": "packet_count"})
    return px.bar(counts, x="station_id", y="packet_count", title="Packets per Station")
