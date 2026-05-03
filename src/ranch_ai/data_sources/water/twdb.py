from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class TWDBWaterDataSource(PlaceholderDataSourceProvider):
    name = "twdb"
    category = "water"
    requires_key = False
    access_level = "free_open_state_optional_service"
    commercial_safe = True
    citation_url = "https://www.twdb.texas.gov/mapping/data-services.asp"
