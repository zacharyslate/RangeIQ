from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class NASSCroplandDataLayerDataSource(PlaceholderDataSourceProvider):
    name = "nass_cdl"
    category = "land"
    requires_key = False
    access_level = "free_open_government_optional_service"
    commercial_safe = True
    citation_url = "https://www.usda.gov/about-usda/news/blog/find-where-your-food-grown-using-nass-cropland-data-layer"
