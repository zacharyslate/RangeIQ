from __future__ import annotations


RAW_PACKET_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw_packets (
    packet_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    source_transport TEXT NOT NULL,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    payload_raw TEXT NOT NULL,
    rssi REAL,
    snr REAL,
    hop_count INTEGER,
    channel TEXT,
    decoded_ok INTEGER NOT NULL,
    error_message TEXT
)
"""

SENSOR_READING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    pasture_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    air_temp_f REAL,
    humidity_pct REAL,
    pressure_hpa REAL,
    rainfall_in REAL,
    soil_moisture_10cm REAL,
    soil_moisture_30cm REAL,
    soil_moisture_60cm REAL,
    soil_temp_f REAL,
    water_tank_pct REAL,
    trough_level_pct REAL,
    battery_voltage REAL,
    solar_voltage REAL,
    signal_strength REAL,
    rssi REAL,
    snr REAL,
    hop_count INTEGER,
    firmware_version TEXT,
    notes TEXT
)
"""

STATION_STATUS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS station_status (
    station_id TEXT PRIMARY KEY,
    last_seen TEXT,
    status TEXT NOT NULL,
    battery_status TEXT NOT NULL,
    signal_status TEXT NOT NULL,
    sensor_error_status TEXT NOT NULL,
    alerts_json TEXT NOT NULL
)
"""
