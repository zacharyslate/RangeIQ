# Free and Open Data Sources for RangeIQ

Last reviewed: April 27, 2026

This document lists the preferred public-data sources for RangeIQ after removing almanac services and login-required vegetation connectors from the active app path.

## Phase 1: Best immediate sources

### NOAA / National Weather Service

- Category: weather, forecast, warnings, fire-weather alerts
- Access: free, open government, no paid key
- Commercial-safe: yes
- Notes: U.S.-only, requires a meaningful `User-Agent` header
- Official docs: <https://www.weather.gov/documentation/services-web-api>

### NASA POWER

- Category: agroclimate, historical weather, radiation, humidity, wind, temperature
- Access: free, open government, no key
- Commercial-safe: yes
- Notes: strong fallback where ranch stations are sparse
- Official docs: <https://power.larc.nasa.gov/docs/services/api/>

### USDA NRCS Soil Data Access / SSURGO

- Category: soil profile, drainage, map unit, water capacity
- Access: free, open government, no key
- Commercial-safe: yes
- Notes: one of the highest-value ranch context sources in the stack
- Official docs: <https://sdmdataaccess.nrcs.usda.gov/>

### U.S. Drought Monitor / Drought.gov

- Category: drought severity and history
- Access: free, open government, no key
- Commercial-safe: yes
- Notes: excellent operational drought baseline
- Official docs: <https://www.drought.gov/data-maps-tools/us-drought-monitor>

### USGS Water Data APIs

- Category: streamflow, gage height, water measurements, monitoring locations
- Access: free, open government; API key optional for higher rate limits
- Commercial-safe: yes
- Notes: modernized OGC/STAC-style water APIs are preferred over older legacy services
- Official docs: <https://api.waterdata.usgs.gov/docs/>

### TexMesonet

- Category: Texas weather-station context
- Access: free, open state service, no key
- Commercial-safe: yes
- Notes: especially valuable for Texas ranch operations
- Official docs: <https://www.texmesonet.org/Apis>

## Phase 2: Useful optional sources

### NASA FIRMS

- Category: active fire / thermal anomalies
- Access: free MAP_KEY required
- Commercial-safe: yes
- Notes: excellent fire signal, but not no-key
- Official docs: <https://firms2.modaps.eosdis.nasa.gov/api/map_key/>

### USDA NASS Quick Stats

- Category: county-level agricultural statistics
- Access: free API key required
- Commercial-safe: yes
- Notes: useful for regional cattle, hay, forage, and production context
- Official docs: <https://quickstats.nass.usda.gov/api>

### Texas Water Development Board data services

- Category: groundwater, aquifers, Texas water planning data
- Access: free/open state services
- Commercial-safe: yes
- Notes: worthwhile Texas expansion area after the core weather/drought/water stack
- Official docs: <https://www.twdb.texas.gov/mapping/data-services.asp>

### EPA AQS

- Category: air quality
- Access: free API key / email registration
- Commercial-safe: generally yes for public data access
- Notes: optional because it adds credentials and is less central than weather, drought, soil, and water for the first ranch deployment
- Official docs: <https://aqs.epa.gov/aqsweb/documents/data_api.html>

## Phase 3: Advanced geospatial layers

### MRLC / NLCD

- Category: land cover
- Access: free, open government
- Commercial-safe: yes
- Notes: high value, but best added once raster/zonal workflows are in place
- Official docs: <https://www.mrlc.gov/home>

### USDA NASS Cropland Data Layer

- Category: land use / crop context
- Access: public/open
- Commercial-safe: likely yes for source data
- Notes: helpful for neighboring land-use context
- Official references: <https://www.usda.gov/about-usda/news/blog/find-where-your-food-grown-using-nass-cropland-data-layer>

### Microsoft Planetary Computer STAC

- Category: advanced satellite / STAC catalog workflows
- Access: advanced optional
- Commercial-safe: review the exact catalog and processing path before production use
- Notes: good future path for Landsat, Sentinel, HLS, burn scars, water detection, and vegetation indices
- Official docs used for current scaffolding: <https://learn.microsoft.com/en-us/azure/planetary-computer/stac-overview>

## Intentionally excluded from the active app path

- Almanac/commercial climatology APIs: removed so RangeIQ stays free/open-first.
- Login-required vegetation connectors: removed until we choose a real no-login vegetation source.
- OAuth-heavy or institution-approval systems: intentionally avoided for the MVP provider registry.
