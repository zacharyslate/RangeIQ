from __future__ import annotations

from ranch_ai.data_sources.base import PlaceholderDataSourceProvider


class EPAAQSDataSource(PlaceholderDataSourceProvider):
    name = "epa_aqs"
    category = "air"
    requires_key = True
    access_level = "free_key_required"
    commercial_safe = True
    citation_url = "https://aqs.epa.gov/aqsweb/documents/data_api.html"
