from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


TIME_RANGE_HOURS = {
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
}


def filter_sensor_time_range(sensor_df: pd.DataFrame, time_range: str) -> pd.DataFrame:
    filtered = sensor_df.sort_values("timestamp").copy()
    if time_range not in TIME_RANGE_HOURS or filtered.empty:
        return filtered
    cutoff = filtered["timestamp"].max() - pd.Timedelta(hours=TIME_RANGE_HOURS[time_range])
    return filtered.loc[filtered["timestamp"] >= cutoff].copy()


def plot_sensor_variable(sensor_df: pd.DataFrame, station_id: str, column: str, title: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    return px.line(station_df, x="timestamp", y=column, title=title, labels={"timestamp": "Timestamp", column: title})


def plot_soil_moisture_comparison(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["soil_moisture_10cm"], mode="lines", name="10 cm"))
    figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["soil_moisture_30cm"], mode="lines", name="30 cm"))
    figure.update_layout(title="Soil Moisture Comparison", xaxis_title="Timestamp", yaxis_title="Moisture (%)")
    return figure


def plot_rainfall_history(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    station_df = station_df.copy()
    station_df["cumulative_rainfall_in"] = station_df["rainfall_in"].cumsum()
    figure = go.Figure()
    figure.add_trace(go.Bar(x=station_df["timestamp"], y=station_df["rainfall_in"], name="Hourly rainfall"))
    figure.add_trace(
        go.Scatter(x=station_df["timestamp"], y=station_df["cumulative_rainfall_in"], mode="lines", name="Cumulative rainfall")
    )
    figure.update_layout(title="Rainfall History", xaxis_title="Timestamp", yaxis_title="Rainfall (in)")
    return figure


def plot_network_soil_moisture(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    figure = go.Figure()
    for column, label in [
        ("soil_moisture_10cm", "10 cm"),
        ("soil_moisture_30cm", "30 cm"),
        ("soil_moisture_60cm", "60 cm"),
    ]:
        if column in station_df.columns and station_df[column].notna().any():
            figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df[column], mode="lines", name=label))
    figure.update_layout(title="Soil Moisture Over Time", xaxis_title="Timestamp", yaxis_title="Moisture (%)")
    return figure


def plot_water_tank_level(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    figure = go.Figure()
    if "water_tank_pct" in station_df.columns:
        figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["water_tank_pct"], mode="lines", name="Tank"))
    if "trough_level_pct" in station_df.columns:
        figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["trough_level_pct"], mode="lines", name="Trough"))
    figure.update_layout(title="Water Storage Levels", xaxis_title="Timestamp", yaxis_title="Level (%)")
    return figure


def plot_battery_voltage(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["battery_voltage"], mode="lines", name="Battery"))
    if "solar_voltage" in station_df.columns:
        figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["solar_voltage"], mode="lines", name="Solar"))
    figure.update_layout(title="Battery and Solar Voltage", xaxis_title="Timestamp", yaxis_title="Voltage")
    return figure


def plot_air_temp_and_humidity(sensor_df: pd.DataFrame, station_id: str):
    station_df = sensor_df.loc[sensor_df["station_id"] == station_id].sort_values("timestamp")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["air_temp_f"], mode="lines", name="Air Temp (F)"))
    figure.add_trace(go.Scatter(x=station_df["timestamp"], y=station_df["humidity_pct"], mode="lines", name="Humidity (%)", yaxis="y2"))
    figure.update_layout(
        title="Air Temperature and Humidity",
        xaxis_title="Timestamp",
        yaxis=dict(title="Temperature (F)"),
        yaxis2=dict(title="Humidity (%)", overlaying="y", side="right"),
    )
    return figure
