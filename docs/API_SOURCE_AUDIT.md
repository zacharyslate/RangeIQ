# RangeIQ API Source Audit

Last reviewed: April 27, 2026

This audit reflects the current RangeIQ codebase after removing almanac integrations and login-required vegetation providers from the active app configuration.

## Active integrations in the app

| Source | Current files | Access type | Keep / change | Env vars | Known restrictions / notes |
| --- | --- | --- | --- | --- | --- |
| NOAA / NWS weather API | `src/ranch_ai/data/weather.py` | `free_open_government` | Keep | none required, but a real `User-Agent` is strongly recommended | Official NWS guidance expects a meaningful `User-Agent` and respectful request rates. |
| NOAA / NWS alerts API | `src/ranch_ai/data/alerts.py` | `free_open_government` | Keep | none required | Good production-safe U.S. source for alerts and warnings. |
| Open-Meteo weather API | `src/ranch_ai/data/weather.py` | `no_key_free_noncommercial` | Keep, but development/research only unless licensing is resolved | none required | The unrestricted free tier is not a clean commercial default. |
| NASA POWER historical weather | `src/ranch_ai/data/public_sources.py` | `free_open_government` | Keep | none | Strong agroclimate history source. |
| USDA NRCS Soil Data Access / SSURGO | `src/ranch_ai/data/public_sources.py` | `free_open_government` | Keep | none | Current implementation uses pasture-centroid soil lookup. |
| U.S. Drought Monitor county statistics + Census geocoder | `src/ranch_ai/data/public_sources.py` | `free_open_government` | Keep | none | Good operational drought proxy. Current implementation is county-based, not ranch-polygon extraction. |
| Mock vegetation history | `src/ranch_ai/data/public_sources.py` | `local_mock_only` | Keep for now | none | Active placeholder until a no-login public vegetation source is selected. |

## Removed from the active app path

| Source | Previous status | Current decision | Reason |
| --- | --- | --- | --- |
| IBM / Weather Company Almanac API | Legacy optional integration | Removed from app configuration and ML path | Outside the free/open-first direction and required credentials. |
| Old Farmer's Almanac placeholder | Legacy scaffold | Removed | No verified supported official integration. |
| NASA AppEEARS vegetation history | Legacy optional integration | Removed from active app configuration | Required login/token management. |
| `usgs_landsat` AppEEARS-based vegetation path | Legacy optional integration | Removed from active app configuration | Despite the provider name, it still depended on Earthdata/AppEEARS credentials. |

## Free/open provider registry status

RangeIQ includes a dedicated provider layer under `src/ranch_ai/data_sources/` with config in `config/api_sources.yaml`.

### Enabled by default

| Provider | Category | Access | Recommendation |
| --- | --- | --- | --- |
| `nws` | weather | free, open government, no key | Primary U.S. operational weather and severe-alert source |
| `open_meteo` | weather | free, no key, non-commercial | Useful fallback for development; not production-safe until licensing is resolved |
| `nasa_power` | weather / climate | free, open government, no key | Strong historical agroclimate source |
| `texmesonet` | weather | free, open state, no key | Good Texas-specific station layer |
| `nrcs_soil_data_access` | soil | free, open government, no key | High-value ranch context source |
| `drought_monitor` | drought | free, open government, no key | Strong drought baseline |
| `usgs_water` | water | free, open government, optional key for higher rate limits | Valuable nearby water-monitoring context |

### Present but disabled by default

| Provider | Category | Access | Reason disabled by default |
| --- | --- | --- | --- |
| `twdb` | water | free/open state services | Current code is scaffold-only |
| `nasa_firms` | fire | free key required | Useful, but key-gated |
| `nlcd_mrlc` | land | free/open government | Raster/zonal work is not implemented yet |
| `nass_cdl` | land | free/open government | Advanced land-use context; scaffold only |
| `nass_quickstats` | agriculture | free key required | Optional when a free key exists |
| `epa_aqs` | air quality | free key required | Credentialed and not yet central to the ranch MVP |
| `planetary_computer` | satellite | advanced optional STAC | Kept as lightweight scaffold only |

## Environment variables still in use

Only the optional keyed providers in the free/open registry use environment variables now:

- `USDA_NASS_API_KEY`
- `NASA_FIRMS_MAP_KEY`
- `USGS_API_KEY`
- `EPA_AQS_EMAIL`
- `EPA_AQS_KEY`
- `RANGEIQ_NWS_USER_AGENT`

Placeholders for these remain in `.env.example`. No almanac or Earthdata credentials are used by the active app anymore.
