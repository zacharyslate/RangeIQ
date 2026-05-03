# Data Schema

## `pastures.geojson`

Each feature should include:

- `pasture_id`
- `name`
- `acres`
- `geometry` as a polygon

Optional helper fields for starter boundary files:

- `boundary_status`
- `source_address`
- `notes`

## Weekly pasture dataset

Primary MVP columns:

- `pasture_id`
- `name`
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
- `estimated_carrying_capacity_au`
- `stocking_ratio`
- `supplement_kg`
- `manual_forage_score`
- `predicted_forage_score`
- `pasture_condition_score`
- `rainfall_deficit_30d`
- `water_risk_score`
- `stocking_risk_score`
- `risk_score`
- `recommendation`

Additional engineered columns in the MVP:

- `soil_moisture_30cm`
- `heat_stress_index`
- `pasture_recovery_score`
- `stress_class`
- `predicted_stress_class`

## `sensor_readings.csv`

Columns prepared for future stationary monitoring stations:

- `station_id`
- `pasture_id`
- `timestamp`
- `air_temp_c`
- `humidity_pct`
- `pressure_hpa`
- `rainfall_mm`
- `soil_moisture_10cm`
- `soil_moisture_30cm`
- `soil_temp_c`
- `battery_voltage`
- `signal_strength`
- `notes`

## `ranchiq_vegetation_history.csv`

Monthly history columns:

- `pasture_id`
- `name`
- `month_start`
- `ndvi_mean`
- `ndvi_baseline`
- `ndvi_anomaly`
- `evi_mean`
- `rainfall_mm`
- `rainfall_baseline_mm`
- `rainfall_deficit_mm`
- `drought_category`
