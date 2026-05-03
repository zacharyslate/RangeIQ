from __future__ import annotations

import html

import pandas as pd
import streamlit as st


def _status_color(status: str) -> str:
    if status == "ONLINE":
        return "#4c7f3a"
    if status == "STALE":
        return "#b4742f"
    return "#8a4730"


def render_station_cards(status_df: pd.DataFrame, latest_readings_df: pd.DataFrame) -> None:
    if status_df.empty:
        st.info("No sensor-network station cards are available.")
        return

    merged = status_df.merge(
        latest_readings_df[["station_id", "air_temp_f", "humidity_pct", "water_tank_pct", "battery_voltage", "rssi"]],
        on="station_id",
        how="left",
        suffixes=("", "_latest"),
    )
    columns = st.columns(min(3, len(merged)))
    for idx, row in enumerate(merged.itertuples(index=False)):
        with columns[idx % len(columns)]:
            alerts = ", ".join(getattr(row, "alerts", [])[:3]) or "No active station alerts"
            station_title = getattr(row, "station_name", row.station_id)
            st.markdown(
                (
                    "<div style='border:1px solid rgba(160,140,110,0.35); border-radius:18px; padding:0.9rem 1rem; "
                    "background:linear-gradient(180deg, rgba(255,255,255,0.04), rgba(0,0,0,0.04)); min-height:170px'>"
                    f"<div style='font-size:0.8rem; letter-spacing:0.08em; text-transform:uppercase; color:#8a7a6a'>"
                    f"{html.escape(row.station_id)}</div>"
                    f"<div style='font-size:1.15rem; font-weight:700; margin:0.2rem 0 0.35rem 0'>{html.escape(station_title)}</div>"
                    f"<div style='display:inline-block; padding:0.18rem 0.6rem; border-radius:999px; background:{_status_color(row.status)}; color:white; font-size:0.76rem; font-weight:700'>{html.escape(row.status)}</div>"
                    f"<div style='margin-top:0.65rem; color:#7d6b58'>Battery {row.battery_voltage if pd.notna(row.battery_voltage) else '--'} V | RSSI {row.rssi if pd.notna(row.rssi) else '--'}</div>"
                    f"<div style='margin-top:0.25rem; color:#7d6b58'>Temp {row.air_temp_f if pd.notna(row.air_temp_f) else '--'} F | Humidity {row.humidity_pct if pd.notna(row.humidity_pct) else '--'}%</div>"
                    f"<div style='margin-top:0.25rem; color:#7d6b58'>Water {row.water_tank_pct if pd.notna(row.water_tank_pct) else '--'}%</div>"
                    f"<div style='margin-top:0.55rem; font-size:0.88rem'>{html.escape(alerts)}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
