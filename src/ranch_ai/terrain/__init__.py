"""USGS 3DEP lidar-derived terrain for saved ranch boundaries."""

from ranch_ai.terrain.analysis import (
    HOLECHEK_SLOPE_CLASSES,
    M_TO_FT,
    TerrainDerivatives,
    compute_derivatives,
    downsample_for_display,
    drape_ring,
    pasture_terrain_stats,
)
from ranch_ai.terrain.dem_client import (
    TerrainGrid,
    TerrainLoadResult,
    TerrainService,
    build_export_image_params,
    compute_request_bounds,
    grid_to_geotiff_bytes,
    plan_raster_size,
    synthetic_terrain,
    utm_epsg_for,
)

__all__ = [
    "HOLECHEK_SLOPE_CLASSES",
    "M_TO_FT",
    "TerrainDerivatives",
    "TerrainGrid",
    "TerrainLoadResult",
    "TerrainService",
    "build_export_image_params",
    "compute_derivatives",
    "compute_request_bounds",
    "downsample_for_display",
    "drape_ring",
    "grid_to_geotiff_bytes",
    "pasture_terrain_stats",
    "plan_raster_size",
    "synthetic_terrain",
    "utm_epsg_for",
]
