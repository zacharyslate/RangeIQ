from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_ndvi_trend(df: pd.DataFrame, pasture_id: str):
    pasture_df = df.loc[df["pasture_id"] == pasture_id].sort_values("week_start")
    return px.line(
        pasture_df,
        x="week_start",
        y=["ndvi_mean", "ndvi_historical_mean"],
        title="Current NDVI Trend",
        labels={"value": "Index value", "week_start": "Week start"},
    )


def plot_rainfall_trend(df: pd.DataFrame, pasture_id: str):
    pasture_df = df.loc[df["pasture_id"] == pasture_id].sort_values("week_start")
    return px.bar(
        pasture_df,
        x="week_start",
        y=["rainfall_7d", "rainfall_30d"],
        barmode="group",
        title="Current Rainfall Trend",
        labels={"value": "Millimeters", "week_start": "Week start"},
    )


def plot_forage_trend(df: pd.DataFrame, pasture_id: str):
    pasture_df = df.loc[df["pasture_id"] == pasture_id].sort_values("week_start")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=pasture_df["week_start"],
            y=pasture_df["manual_forage_score"],
            mode="lines+markers",
            name="Reference forage score",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=pasture_df["week_start"],
            y=pasture_df["predicted_forage_score"],
            mode="lines+markers",
            name="Predicted forage score",
        )
    )
    figure.update_layout(title="Forage Score Trend", xaxis_title="Week start", yaxis_title="Score")
    return figure


def plot_recommendation_mix(df: pd.DataFrame, recommendation_colors: dict[str, str] | None = None):
    counts = df["recommendation"].value_counts().rename_axis("recommendation").reset_index(name="count")
    return px.bar(
        counts,
        x="recommendation",
        y="count",
        color="recommendation",
        title="Current Recommendation Mix",
        color_discrete_map=recommendation_colors,
    )


def plot_condition_scores(df: pd.DataFrame, recommendation_colors: dict[str, str] | None = None):
    ordered = df.sort_values("pasture_condition_score", ascending=True)
    return px.bar(
        ordered,
        x="pasture_condition_score",
        y="name",
        orientation="h",
        color="recommendation",
        title="Pasture Condition Score",
        labels={"pasture_condition_score": "Condition score", "name": "Pasture"},
        color_discrete_map=recommendation_colors,
    )


def plot_long_term_vegetation_history(history_df: pd.DataFrame, pasture_id: str):
    pasture_df = history_df.loc[history_df["pasture_id"] == pasture_id].sort_values("month_start")
    return px.line(
        pasture_df,
        x="month_start",
        y=["ndvi_mean", "ndvi_baseline"],
        title="10-Year Vegetation History",
        labels={"value": "Vegetation index", "month_start": "Month"},
    )


def plot_rainfall_deficit_history(history_df: pd.DataFrame, pasture_id: str):
    pasture_df = history_df.loc[history_df["pasture_id"] == pasture_id].sort_values("month_start")
    return px.bar(
        pasture_df,
        x="month_start",
        y="rainfall_deficit_mm",
        title="Monthly Rainfall Deficit History",
        labels={"rainfall_deficit_mm": "Rainfall deficit (mm)", "month_start": "Month"},
    )


def plot_water_vs_stocking_risk(df: pd.DataFrame, recommendation_colors: dict[str, str] | None = None):
    return px.scatter(
        df,
        x="water_risk_score",
        y="stocking_risk_score",
        color="recommendation",
        size="pasture_condition_score",
        hover_name="name",
        title="Water Risk vs Stocking Risk",
        labels={
            "water_risk_score": "Water risk score",
            "stocking_risk_score": "Stocking risk score",
            "pasture_condition_score": "Condition score",
        },
        color_discrete_map=recommendation_colors,
    )


def plot_public_ndvi_history(ndvi_df: pd.DataFrame, pasture_id: str):
    pasture_df = ndvi_df.loc[ndvi_df["pasture_id"] == pasture_id].sort_values("month_start")
    if pasture_df.empty:
        return go.Figure().update_layout(title="NDVI History Unavailable")
    aggregation_mode = str(pasture_df.get("aggregation_mode", pd.Series(["monthly_median"])).iloc[-1]).replace("_", " ").title()
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=pasture_df["month_start"],
            y=pasture_df["ndvi_mean"],
            mode="lines+markers",
            name="NDVI",
        )
    )
    if "historical_mean" in pasture_df.columns:
        figure.add_trace(
            go.Scatter(
                x=pasture_df["month_start"],
                y=pasture_df["historical_mean"],
                mode="lines",
                name="Seasonal normal",
                line=dict(dash="dash"),
            )
        )
    figure.update_layout(
        title=f"Short-Term Greenness (NDVI {aggregation_mode})",
        xaxis_title="Month",
        yaxis_title="NDVI",
    )
    return figure


def plot_rap_cover_history(cover_df: pd.DataFrame, pasture_id: str):
    pasture_df = cover_df.loc[cover_df["pasture_id"] == pasture_id].sort_values("year")
    if pasture_df.empty:
        return go.Figure().update_layout(title="RAP Cover History Unavailable")
    figure = go.Figure()
    for column, label in [
        ("rap_perennial_grass_forb_cover_pct", "Perennial grass/forb"),
        ("rap_annual_grass_forb_cover_pct", "Annual grass/forb"),
        ("rap_shrub_cover_pct", "Shrub"),
        ("rap_tree_cover_pct", "Tree"),
        ("rap_bare_ground_pct", "Bare ground"),
    ]:
        if column in pasture_df.columns:
            figure.add_trace(
                go.Scatter(
                    x=pasture_df["year"],
                    y=pasture_df[column],
                    mode="lines+markers",
                    name=label,
                )
            )
    figure.update_layout(
        title="RAP Long-Term Rangeland Structure",
        xaxis_title="Year",
        yaxis_title="Cover (%)",
    )
    return figure


def plot_rap_production_history(production_df: pd.DataFrame, pasture_id: str):
    pasture_df = production_df.loc[production_df["pasture_id"] == pasture_id].sort_values("year")
    if pasture_df.empty:
        return go.Figure().update_layout(title="RAP Production History Unavailable")
    figure = go.Figure()
    for column, label in [
        ("rap_total_herbaceous_production_lb_ac", "Total herbaceous"),
        ("rap_perennial_production_lb_ac", "Perennial"),
        ("rap_annual_production_lb_ac", "Annual"),
    ]:
        if column in pasture_df.columns:
            figure.add_trace(
                go.Scatter(
                    x=pasture_df["year"],
                    y=pasture_df[column],
                    mode="lines+markers",
                    name=label,
                )
            )
    figure.update_layout(
        title="RAP Production History",
        xaxis_title="Year",
        yaxis_title="lbs / acre",
    )
    return figure
