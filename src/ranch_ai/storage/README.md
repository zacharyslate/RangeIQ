# Storage Package

RangeIQ currently uses a lightweight SQLite store for the sensor-network MVP.

Tables:

- `raw_packets`
- `sensor_readings`
- `station_status`

The abstraction layer is intentionally small so we can add Postgres later for a ranch base-station deployment without changing the ingestion and dashboard contracts.
