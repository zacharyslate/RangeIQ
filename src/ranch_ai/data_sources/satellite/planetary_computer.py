from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class PlanetaryComputerDataSource(PlaceholderDataSourceProvider):
    name = "planetary_computer"
    category = "satellite"
    requires_key = False
    access_level = "advanced_optional_stac"
    commercial_safe = True
    citation_url = "https://learn.microsoft.com/en-us/azure/planetary-computer/stac-overview"
