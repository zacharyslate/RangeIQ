from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class NLCDMRLCDataSource(PlaceholderDataSourceProvider):
    name = "nlcd_mrlc"
    category = "land"
    requires_key = False
    access_level = "free_open_government_advanced_raster"
    commercial_safe = True
    citation_url = "https://www.mrlc.gov/home"
