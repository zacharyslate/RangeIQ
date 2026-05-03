# RangeIQ

RangeIQ is a synthetic-data-first ranch intelligence MVP for West Texas ranch operations. It keeps the pasture recommendation pipeline in place and now opens on a practical operational dashboard with weather, alerts, fire risk, and station monitoring.

The default ranch is now **Caja Caliente** at `711 N Scotty Road, Alpine, TX 79830`. The bundled default boundary is a single rectangular pasture drawn from your provided property corners.

## What the app does

- Runs offline with mock weather, mock alerts, mock sensors, and synthetic pasture-week data.
- Supports optional public providers:
  - weather: `mock`, `nws`, `openmeteo`
  - alerts: `mock`, `nws`
  - sensors: `csv`, `mock`
- Includes a hybrid public-data training layer for:
  - historical weather: `mock`, `nasa_power`
  - soils: `mock`, `usda_sda`
  - drought: `mock`, `usdm`
  - vegetation history: `mock`, `earth_search_stac`, `climate_engine`
- Shows:
  - current weather
  - 7-day forecast
  - active warnings
  - fire and drought risk
- ranch map
- pasture summary and recommendations
- vegetation history and range health
- sensor station status and plots
- sensor-network mock telemetry, raw packets, and mesh health
- provider mode and fallback status

The ranch map now defaults to free **USGS NAIP aerial imagery** for a clearer small-property view, with automatic fallback to the standard map if that imagery is unavailable.

## Quickstart

```bash
pip install -e .
streamlit run app/dashboard.py
```

Optional CLI run:

```bash
python -m ranch_ai --weeks 12 --history-years 5
```

On Windows you can launch with [Launch RangeIQ.cmd](</C:/Users/zacha/OneDrive/Documents/New project 2/Launch RangeIQ.cmd>) or double-click [RangeIQ Dashboard.lnk](</C:/Users/zacha/OneDrive/Documents/New project 2/RangeIQ Dashboard.lnk>).

Boundary uploads in the dashboard now accept `GeoJSON`, `JSON`, `KML`, and `KMZ`.

To keep your setup between launches, open the `Settings` tab and click `Save Current Setup`. RangeIQ now saves settings and uploaded boundaries per `Workspace ID`, so different users can keep separate setups without overwriting one another. Bookmark the current URL after saving if you want the same workspace to reopen later.

## GitHub And Launch Prep

RangeIQ is now structured so it can be placed directly into a GitHub repository and deployed from there.

Repository-friendly defaults:

- local machine state like `config.yaml`, saved dashboard state, cached pulls, generated outputs, and uploaded personal boundary files are ignored by Git
- the Streamlit Cloud entrypoint is [streamlit_app.py](</C:/Users/zacha/OneDrive/Documents/New project 2/streamlit_app.py>)
- Streamlit runtime settings live in [.streamlit/config.toml](</C:/Users/zacha/OneDrive/Documents/New project 2/.streamlit/config.toml>)
- Python dependencies are declared in both [pyproject.toml](</C:/Users/zacha/OneDrive/Documents/New project 2/pyproject.toml>) and [requirements.txt](</C:/Users/zacha/OneDrive/Documents/New project 2/requirements.txt>)

Recommended publish flow:

1. Create an empty GitHub repository named `RangeIQ`
2. Put this project into that repo
3. Deploy it from GitHub to Streamlit Community Cloud
4. Add any optional API keys or secrets in the Streamlit deployment settings, not in the repo

Current hosted deploy settings:

- GitHub repo: `zacharyslate/RangeIQ`
- Branch: `main`
- Main file path: `streamlit_app.py`

Streamlit Community Cloud checklist:

1. Open [Streamlit Community Cloud](https://share.streamlit.io/) and create a new app
2. Select repository `zacharyslate/RangeIQ`
3. Select branch `main`
4. Set the entrypoint to `streamlit_app.py`
5. Add any optional secrets only if you decide to enable non-mock providers later
6. Deploy

Useful official references:

- [Deploy your app on Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Manage app secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

## Deploy On A DigitalOcean Droplet

For a faster US-hosted deployment than Streamlit Community Cloud, RangeIQ can run on a Linux VM and sit behind a reverse proxy.

Recommended shape:

- Ubuntu Droplet in a US region
- RangeIQ bound to `127.0.0.1:8501`
- Caddy or Nginx reverse proxy in front
- systemd service so the app restarts automatically

Deployment helper files:

- [bootstrap_rangeiq.sh](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/ubuntu/bootstrap_rangeiq.sh>)
- [rangeiq.service.example](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/systemd/rangeiq.service.example>)
- [Caddyfile.example](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/caddy/Caddyfile.example>)
- [rangeiq.env.example](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/env/rangeiq.env.example>)

Typical Ubuntu flow:

```bash
ssh root@YOUR_DROPLET_IP
git clone https://github.com/zacharyslate/RangeIQ.git
cd RangeIQ
bash deploy/ubuntu/bootstrap_rangeiq.sh
sudo mkdir -p /etc/rangeiq
sudo cp deploy/env/rangeiq.env.example /etc/rangeiq/rangeiq.env
sudo cp deploy/systemd/rangeiq.service.example /etc/systemd/system/rangeiq.service
sudo systemctl daemon-reload
sudo systemctl enable --now rangeiq
sudo systemctl status rangeiq
```

The service runs Streamlit only on localhost:

```text
127.0.0.1:8501
```

Then put a reverse proxy in front of it. With Caddy, use [Caddyfile.example](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/caddy/Caddyfile.example>) and replace `rangeiq.example.com` with your real domain.

This is safer than exposing Streamlit directly because the app is not bound to the public interface.

### Auto Deploy From GitHub

RangeIQ can now redeploy itself to the Droplet automatically whenever `main` is updated.

Workflow file:

- [.github/workflows/deploy-droplet.yml](</C:/Users/zacha/OneDrive/Documents/New project 2/.github/workflows/deploy-droplet.yml>)

Server update helper:

- [update_rangeiq.sh](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/ubuntu/update_rangeiq.sh>)

GitHub repository secrets to add:

- `DROPLET_HOST`
  - Example: `138.197.143.23`
- `DROPLET_USER`
  - Recommended first setup: `root`
- `DROPLET_SSH_PRIVATE_KEY`
  - The private key GitHub Actions should use to SSH into the Droplet
- `DROPLET_SSH_PORT`
  - Optional; defaults to `22`

Recommended flow:

1. Use an SSH key that already has login access to the Droplet, or create a dedicated deploy key pair.
2. Put the private key into the GitHub repository secret `DROPLET_SSH_PRIVATE_KEY`.
3. Make sure the matching public key is present in the target server user's `~/.ssh/authorized_keys`.
4. Keep the app checkout at `/opt/rangeiq`, because the workflow deploys there by default.
5. Push to `main`, or manually run the `Deploy Droplet` workflow from the GitHub Actions tab.

What the workflow does:

- SSH into the Droplet
- `git pull --ff-only origin main`
- refresh the editable install in `/opt/rangeiq/.venv`
- restart `rangeiq.service`
- print the latest service logs
- keep the same steps available manually through [update_rangeiq.sh](</C:/Users/zacha/OneDrive/Documents/New project 2/deploy/ubuntu/update_rangeiq.sh>)

Manual fallback on the server:

```bash
cd /opt/rangeiq
bash deploy/ubuntu/update_rangeiq.sh
```

## Vegetation History

RangeIQ now combines two different vegetation signals:

- `NDVI` for short-term greenness:
  - answers whether a pasture is greener or less green than normal for this time of year
- `RAP` for long-term rangeland structure:
  - answers whether perennial grass, bare ground, shrubs, and production are improving or slipping over time

The `Pastures` tab now includes:

- current greenness status
- NDVI anomaly versus seasonal normal
- perennial grass, bare ground, shrub, and production trends
- a transparent `RangeIQ Vegetation Health Score`
- NDVI, RAP cover, and RAP production charts

Mock mode works offline by default. The default live NDVI provider is:

- `NDVI_PROVIDER=earth_search_stac`

Required environment variables:

- `EARTH_SEARCH_STAC_URL`
- `NDVI_DEFAULT_COLLECTION`
- `NDVI_CLOUD_COVER_MAX`
- `VEGETATION_CACHE_TTL_DAYS`

Optional providers and legacy credentials:

- `CLIMATE_ENGINE_API_KEY`
- `APPEEARS_USERNAME`
- `APPEEARS_PASSWORD`

AppEEARS is retained only as a legacy optional fallback because its login token workflow expires quickly. RangeIQ no longer depends on AppEEARS to run Vegetation History.

RAP does not require a key. RangeIQ caches vegetation pulls under `data/cache/vegetation` so repeated ranch requests can be reused offline and so large history calls are not repeated unnecessarily.

## Sensor Network MVP

RangeIQ now includes a mock-ready Meshtastic/LoRa sensor-network architecture with:

- station schemas and status classification
- compact telemetry packet parsing and encoding
- mock and CSV-backed transport clients
- SQLite storage for raw packets, normalized readings, and station status
- a dedicated `Sensor Network` dashboard tab

Key example assets:

- [sensor_stations.example.csv](</C:/Users/zacha/OneDrive/Documents/New project 2/data/sensors/sensor_stations.example.csv>)
- [sensor_readings.example.csv](</C:/Users/zacha/OneDrive/Documents/New project 2/data/sensors/sensor_readings.example.csv>)
- [raw_packets.example.jsonl](</C:/Users/zacha/OneDrive/Documents/New project 2/data/sensors/raw_packets.example.jsonl>)
- [rangeiq.example.yaml](</C:/Users/zacha/OneDrive/Documents/New project 2/config/rangeiq.example.yaml>)

Generate or refresh the example network bundle with:

```bash
PYTHONPATH=src python scripts/generate_mock_sensor_network.py
```

## Default ranch boundary

The included starter GeoJSON is [caja_caliente_ranch.geojson](</C:/Users/zacha/OneDrive/Documents/New project 2/data/example/caja_caliente_ranch.geojson>).

- Ranch name: `Caja Caliente`
- Address: `711 N Scotty Road, Alpine, TX 79830`
- Pastures: `1`
- Pasture name: `Caja Caliente Main Pasture`
- Approximate area from the provided corners: `4.77 acres`

Corner coordinates used:

- `29°36'24.0"N 103°30'30.1"W`
- `29°36'23.9"N 103°30'40.2"W`
- `29°36'21.6"N 103°30'40.1"W`
- `29°36'21.7"N 103°30'30.0"W`

## Mock mode and fallbacks

No API keys are required.

Default behavior:

- weather provider: `openmeteo`
- alerts provider: `nws`
- sensor provider: paused in the hosted dashboard while under development
- historical weather provider: `nasa_power`
- soils provider: `usda_sda`
- drought provider: `usdm`
- vegetation provider: `earth_search_stac` by default, with optional `mock`, `climate_engine`, or legacy `appeears`

If a public request fails, the dashboard stays up and marks that component as `fallback-mock`.

## Workspaces

RangeIQ now uses lightweight workspace isolation for hosted use:

- each browser session gets a `workspace` ID in the URL
- `Save Current Setup` writes settings and uploaded boundaries to that workspace only
- different users can use different workspace IDs to avoid overwriting one another
- reopening the same workspace is as simple as revisiting or bookmarking the same URL

Important note:

- this is workspace-based separation, not full user authentication
- if two people intentionally use the same workspace ID, they will share and overwrite the same saved setup

Public historical sources are also cached on disk under `data/cache/public_data`, so RangeIQ can:

- reuse recent large pulls without re-hitting the source
- fall back to cached data when you are offline
- avoid unnecessary public API refreshes

## Free/Open source registry

RangeIQ now also includes a dedicated provider registry under [src/ranch_ai/data_sources](</C:/Users/zacha/OneDrive/Documents/New project 2/src/ranch_ai/data_sources>) for auditing and expanding free/open integrations without disturbing the existing dashboard pipeline.

Key files:

- [config/api_sources.yaml](</C:/Users/zacha/OneDrive/Documents/New project 2/config/api_sources.yaml>)
- [docs/API_SOURCE_AUDIT.md](</C:/Users/zacha/OneDrive/Documents/New project 2/docs/API_SOURCE_AUDIT.md>)
- [docs/FREE_DATA_SOURCES.md](</C:/Users/zacha/OneDrive/Documents/New project 2/docs/FREE_DATA_SOURCES.md>)
- [.env.example](</C:/Users/zacha/OneDrive/Documents/New project 2/.env.example>)

You can print the provider readiness report with:

```bash
python -m ranch_ai --check-api-sources
```

Default registry behavior:

- free/open government and state sources are enabled where practical
- no-key but non-commercial sources stay clearly marked
- key-required sources are optional and disabled by default
- paid or enterprise-leaning sources stay outside the default free/open path

## Public Data and ML

RangeIQ now builds a hybrid training dataset that combines:

- synthetic pasture-week features
- weekly sensor aggregates
- public-data feature slots

What is live now:

- `NASA POWER` historical point weather is implemented as an optional source
- `USDA Soil Data Access` point-based soils are implemented as an optional source
- `U.S. Drought Monitor` county-based drought history is implemented as an optional source
- `NOAA / NWS` live operational weather and alerts are implemented
- `RAP` cover and production history are implemented
- `Earth Search STAC` NDVI from Sentinel-2 is the default live provider
- `Climate Engine` NDVI remains implemented as an optional provider
- `AppEEARS` NDVI is retained only as a legacy fallback scaffold

What is scaffolded for the next step:

- deeper NDVI provider options such as Landsat or other STAC collections
- optional RAP 16-day production views in the dashboard

Current drought note: the live `usdm` connector resolves the ranch location to a county using the official Census geocoder, then pulls weekly county statistics from the official U.S. Drought Monitor data service. That is a useful operational proxy, but it is not yet ranch-boundary polygon extraction.

Current vegetation note: NDVI and RAP are intentionally shown as different signals. NDVI is short-term greenness; RAP is long-term rangeland structure and production. A pasture can look green right now while still showing weakening perennial grass or increasing bare ground over the long run. RangeIQ now calculates NDVI itself from Sentinel-2 Red (`B04`) and NIR (`B08`) bands through Element84 Earth Search STAC, then aggregates the series to `monthly_median` by default to reduce noisy cloudy-scene swings.

## Configuration

The app reads `config.yaml` if present. Start from [config.example.yaml](</C:/Users/zacha/OneDrive/Documents/New project 2/config.example.yaml>).

Example:

```yaml
ranch:
  name: "Caja Caliente"
  address: "711 N Scotty Road, Alpine, TX 79830"
  latitude: 29.606333
  longitude: -103.509750

weather:
  provider: "openmeteo"
  user_agent: "RangeIQ/0.1 (contact@example.com)"

alerts:
  provider: "nws"

sensors:
  provider: "csv"
  csv_path: "data/sensors/sensor_readings.csv"

public_data:
  cache_enabled: true
  historical_weather:
    provider: "nasa_power"
    refresh_hours: 168
  soils:
    provider: "usda_sda"
    refresh_hours: 720
  drought:
    provider: "usdm"
    refresh_hours: 48
  vegetation:
    provider: "earth_search_stac"  # or mock, climate_engine, appeears
    refresh_hours: 336
    ndvi_refresh_hours: 168
    rap_refresh_hours: 720
    earth_search_stac_url: "https://earth-search.aws.element84.com/v1"
    ndvi_default_collection: "sentinel-2-l2a"
    ndvi_cloud_cover_max: 30
    ndvi_temporal_aggregation: "monthly_median"
```

To test the live vegetation feature:

1. Keep the default ranch boundary or upload a ranch/pasture polygon.
2. Reinstall the project after pulling the latest changes so `rasterio` is available for live NDVI reads.
3. Start the app with `streamlit run app/dashboard.py`.
4. In `Settings`, leave `Vegetation` on `earth_search_stac` or switch it back to that provider.
5. Open the `Pastures` tab and look for the `Vegetation History / Range Health` section.
6. The vegetation card should show `NDVI source: Earth Search STAC / Sentinel-2` when live STAC NDVI is working.

If a live vegetation provider is unavailable, RangeIQ keeps the panel working with mock data and shows a warning instead of failing the dashboard.

## Sensor CSV schema

```csv
station_id,pasture_id,timestamp,air_temp_f,humidity_pct,pressure_hpa,rainfall_in,soil_moisture_10cm,soil_moisture_30cm,soil_temp_f,battery_voltage,signal_strength,water_tank_pct,trough_level_pct,camera_status,notes
```

## Fire risk logic

The initial fire-risk score is rule-based and uses:

- active fire-weather alerts
- wind speed and gusts
- humidity
- temperature
- short-term rainfall
- drought category
- sensor soil moisture
- recent sensor rainfall
- low water-storage warnings

Categories:

- `LOW`
- `MODERATE`
- `HIGH`
- `VERY HIGH`
- `EXTREME`

## Outputs

Running the pipeline writes:

- `data/processed/pasture_week_data.csv`
- `data/processed/pasture_week_scored.csv`
- `data/processed/rangeiq_vegetation_history.csv`
- `data/processed/rangeiq_monthly_report.csv`
- `data/processed/rangeiq_monthly_report.md`
- `data/sensors/sensor_readings.csv`

The pipeline also creates an in-memory hybrid ML training dataset and surfaces its source status in the dashboard `Data` tab.

## Testing

```bash
python -m pytest
```

## Disclaimer

RangeIQ is decision support only. It does not replace official National Weather Service alerts, local fire authorities, emergency instructions, evacuation orders, or on-the-ground ranch judgment.
