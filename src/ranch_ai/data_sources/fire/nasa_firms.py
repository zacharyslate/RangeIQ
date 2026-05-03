from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class NasaFIRMSDataSource(PlaceholderDataSourceProvider):
    name = "nasa_firms"
    category = "fire"
    requires_key = True
    access_level = "free_key_required"
    commercial_safe = True
    citation_url = "https://firms2.modaps.eosdis.nasa.gov/api/map_key/"
