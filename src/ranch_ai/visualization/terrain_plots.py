"""Plotly 3D terrain figure for the saved ranch boundary."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ranch_ai.terrain.analysis import (
    HOLECHEK_SLOPE_CLASSES,
    M_TO_FT,
    TerrainDerivatives,
    downsample_for_display,
    drape_ring,
    grazing_scale_slope_pct,
)
from ranch_ai.terrain.dem_client import TerrainGrid

TERRAIN_LAYERS = ["Elevation", "Slope (%)", "Grazing slope class", "Hillshade"]

_SLOPE_CLASS_COLORS = ["#4f7d3a", "#d9b44a", "#c8663a", "#7a2e2e"]


def _slope_class_index(slope_pct: np.ndarray) -> np.ndarray:
    out = np.full(slope_pct.shape, np.nan, dtype="float32")
    for index, (_, lower, upper, _) in enumerate(HOLECHEK_SLOPE_CLASSES):
        out[(slope_pct > lower) & (slope_pct <= upper)] = index
    return out


def _discrete_colorscale(colors: list[str]) -> list[list[object]]:
    scale: list[list[object]] = []
    count = len(colors)
    for index, color in enumerate(colors):
        scale.append([index / count, color])
        scale.append([(index + 1) / count, color])
    return scale


def build_terrain_figure(
    grid: TerrainGrid,
    derivatives: TerrainDerivatives,
    pastures: pd.DataFrame,
    *,
    layer: str = "Elevation",
    exaggeration: float = 1.5,
    grazing_slope_window_m: float = 10.0,
    text_color: str = "#241a13",
    background: str = "rgba(0,0,0,0)",
    boundary_color: str = "#f2f2f2",
    height: int = 620,
    max_side: int = 260,
) -> go.Figure:
    if layer == "Slope (%)":
        values = np.clip(derivatives.slope_pct, 0, 80)
        colorscale: object = "YlOrRd"
        colorbar = dict(title="Slope %")
        cmin, cmax = 0.0, float(np.nanpercentile(values, 99)) if np.isfinite(values).any() else 1.0
    elif layer == "Grazing slope class":
        values = _slope_class_index(grazing_scale_slope_pct(grid, grazing_slope_window_m))
        colorscale = _discrete_colorscale(_SLOPE_CLASS_COLORS)
        colorbar = dict(
            title="Slope class",
            tickvals=[0.375, 1.125, 1.875, 2.625],
            ticktext=[label for label, *_ in HOLECHEK_SLOPE_CLASSES],
        )
        cmin, cmax = 0.0, 3.0
    elif layer == "Hillshade":
        values = derivatives.hillshade
        colorscale = "gray"
        colorbar = dict(title="Shade")
        cmin, cmax = 0.0, 1.0
    else:
        values = grid.elevation_m * M_TO_FT
        colorscale = "earth"
        colorbar = dict(title="Elev (ft)")
        finite = values[np.isfinite(values)]
        cmin, cmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)

    x, y, z_m, color = downsample_for_display(grid, values, max_side=max_side)
    z = z_m * M_TO_FT  # display in feet to match the colour bar and stats table
    figure = go.Figure()
    figure.add_trace(
        go.Surface(
            x=x,
            y=y,
            z=z,
            surfacecolor=color,
            colorscale=colorscale,
            cmin=cmin,
            cmax=cmax,
            colorbar=dict(len=0.6, thickness=14, **colorbar),
            lighting=dict(ambient=0.55, diffuse=0.8, specular=0.05, roughness=0.9),
            lightposition=dict(x=-1e5, y=1e5, z=1e5),
            hovertemplate="E %{x:.0f} m<br>N %{y:.0f} m<br>Elev %{z:,.1f} ft<extra></extra>",
            name="Terrain",
        )
    )

    finite_z = z[np.isfinite(z)]
    z_lift = 1.5 if finite_z.size == 0 else max(1.5, 0.004 * float(finite_z.max() - finite_z.min()))
    for record in pastures.itertuples(index=False):
        ring = record.geometry if not isinstance(record.geometry, str) else json.loads(record.geometry)
        bx, by, bz = drape_ring(grid, ring)
        figure.add_trace(
            go.Scatter3d(
                x=bx,
                y=by,
                z=bz * M_TO_FT + z_lift,
                mode="lines",
                line=dict(color=boundary_color, width=6),
                name=str(getattr(record, "name", record.pasture_id)),
                hoverinfo="name",
            )
        )

    x_span = float(x.max() - x.min()) if x.size > 1 else 1.0
    y_span = float(y.max() - y.min()) if y.size > 1 else 1.0
    z_span = float(finite_z.max() - finite_z.min()) / M_TO_FT if finite_z.size else 1.0  # metres, same units as x/y
    longest = max(x_span, y_span, 1.0)
    figure.update_layout(
        height=height,
        paper_bgcolor=background,
        font=dict(color=text_color),
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=0.02),
        scene=dict(
            xaxis=dict(title="East (m)", showbackground=False),
            yaxis=dict(title="North (m)", showbackground=False),
            zaxis=dict(title="Elev (ft, NAVD88)", showbackground=False, nticks=4),
            aspectmode="manual",
            aspectratio=dict(
                x=x_span / longest,
                y=y_span / longest,
                z=max(z_span * exaggeration / longest, 0.02),
            ),
            camera=dict(eye=dict(x=-0.85, y=-0.95, z=0.55)),
        ),
    )
    return figure
