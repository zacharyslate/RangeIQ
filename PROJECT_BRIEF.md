# Texas Ranch AI - MVP Build Brief

## Goal

Build a Python-based MVP decision-support system for optimizing a cattle ranch near Baird, Texas, using free public data first, then allowing local stationary monitoring data to improve predictions over time.

The system should help estimate pasture condition, forage availability, drought stress, grazing pressure, and basic stocking recommendations.

## Philosophy

This is not a black-box AI app. It should be a transparent ranch decision-support system.

The first version should focus on pasture-level optimization, not individual cow-level prediction.

Primary objective:

- Maximize ranch productivity and profit per acre while protecting pasture health.

Secondary objectives:

- Estimate forage condition.
- Track drought stress.
- Recommend graze/rest/supplement/destock actions.
- Prepare the structure for future sensor stations and cattle performance data.

## Location

Target region:

- Baird, Texas
- Callahan County, Texas
- Semi-arid / drought-prone ranching environment

## Free Public Data Sources to Support

Design the code so these sources can be added progressively:

1. NASA / satellite vegetation
   - MODIS NDVI/EVI
   - Landsat
   - Sentinel-2
   - NASA AppEEARS-compatible workflow if possible
2. Weather
   - NOAA Climate Data Online
   - NASA POWER
3. Soil
   - USDA NRCS Web Soil Survey
   - SSURGO / Soil Data Access
4. Drought
   - U.S. Drought Monitor
5. Land cover
   - USDA NASS Cropland Data Layer
6. Topography
   - USGS elevation / slope data

## MVP Requirements

Build the project as a Python package with a clear folder structure.

The first MVP should support:

1. Pasture boundary input
   - GeoJSON or shapefile
   - Each pasture should have:
     - `pasture_id`
     - `name`
     - `acres`
     - polygon geometry
2. Weekly pasture table
   Generate a pasture-week dataset with columns like:
   - `pasture_id`
   - `week_start`
   - `acres`
   - `rainfall_7d`
   - `rainfall_30d`
   - `rainfall_90d`
   - `temp_avg_7d`
   - `temp_max_7d`
   - `drought_category`
   - `ndvi_mean`
   - `ndvi_anomaly`
   - `evi_mean`
   - `soil_type`
   - `soil_water_capacity`
   - `dominant_forage`
   - `days_since_grazed`
   - `animal_units_present`
   - `grazing_pressure`
   - `supplement_kg`
   - `manual_forage_score`
   - `predicted_forage_score`
   - `risk_score`
   - `recommendation`
3. Data ingestion modules
   Create placeholder modules first, even if the API connections are added later:
   - `src/data/weather.py`
   - `src/data/satellite.py`
   - `src/data/soil.py`
   - `src/data/drought.py`
   - `src/data/grazing_records.py`
   - `src/data/sensors.py`
4. Feature engineering
   Create functions for:
   - rainfall rolling sums
   - NDVI anomaly vs historical average
   - grazing pressure
   - days since grazed
   - heat stress index
   - drought risk score
   - pasture recovery score
5. Modeling
   Start with scikit-learn.
   Create models for:
   - forage score prediction
   - drought/pasture stress classification
   - simple stocking recommendation
   Use:
   - `RandomForestRegressor`
   - `GradientBoostingRegressor`
   - `RandomForestClassifier`
6. Optimization
   Add a simple rule-based optimizer first.
   Example recommendations:
   - `GRAZE`
   - `REST`
   - `SUPPLEMENT`
   - `REDUCE STOCKING`
   - `DESTOCK WARNING`
7. Dashboard
   Create a simple Streamlit or Dash dashboard that shows:
   - pasture map
   - pasture condition table
   - NDVI trend
   - rainfall trend
   - drought status
   - stocking recommendation
8. Local sensor integration
   Prepare a CSV schema for future stationary monitoring stations.
9. Example data
   Generate synthetic example data so the app can run without external API keys.
10. Documentation
   Add:
   - `README.md`
   - setup instructions
   - data schema
   - roadmap
   - example workflow

## First Codex Task

Create the initial repository structure and MVP Python files.

The first runnable version should:

1. Generate synthetic pasture-week data.
2. Train a basic forage prediction model.
3. Generate rule-based recommendations.
4. Launch a simple dashboard showing:
   - pasture table
   - predicted forage score
   - drought risk
   - recommendation
   - simple time-series plots

Use clean, modular Python code. Add comments where helpful. Do not over-engineer the first version.

