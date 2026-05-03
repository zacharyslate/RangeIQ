from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from ranch_ai.sensors.schema import SensorReading, StationStatus
from ranch_ai.storage.database import SensorNetworkStore
from ranch_ai.storage.migrations import RAW_PACKET_TABLE_SQL, SENSOR_READING_TABLE_SQL, STATION_STATUS_TABLE_SQL
from ranch_ai.telemetry.packet_schema import RawPacket


class SQLiteStore(SensorNetworkStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def create_tables(self) -> None:
        with self.connection:
            self.connection.execute(RAW_PACKET_TABLE_SQL)
            self.connection.execute(SENSOR_READING_TABLE_SQL)
            self.connection.execute(STATION_STATUS_TABLE_SQL)

    def reset(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM raw_packets")
            self.connection.execute("DELETE FROM sensor_readings")
            self.connection.execute("DELETE FROM station_status")

    def save_raw_packet(self, raw_packet: RawPacket) -> None:
        payload = raw_packet.to_record()
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO raw_packets
                (packet_id, received_at, source_transport, from_node, to_node, payload_raw, rssi, snr, hop_count, channel, decoded_ok, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["packet_id"],
                    pd.Timestamp(payload["received_at"]).isoformat(),
                    payload["source_transport"],
                    payload["from_node"],
                    payload["to_node"],
                    payload["payload_raw"],
                    payload["rssi"],
                    payload["snr"],
                    payload["hop_count"],
                    payload["channel"],
                    1 if payload["decoded_ok"] else 0,
                    payload["error_message"],
                ),
            )

    def save_sensor_reading(self, reading: SensorReading) -> None:
        payload = reading.to_record()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO sensor_readings
                (station_id, pasture_id, timestamp, air_temp_f, humidity_pct, pressure_hpa, rainfall_in, soil_moisture_10cm, soil_moisture_30cm, soil_moisture_60cm, soil_temp_f, water_tank_pct, trough_level_pct, battery_voltage, solar_voltage, signal_strength, rssi, snr, hop_count, firmware_version, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["station_id"],
                    payload["pasture_id"],
                    pd.Timestamp(payload["timestamp"]).isoformat(),
                    payload["air_temp_f"],
                    payload["humidity_pct"],
                    payload["pressure_hpa"],
                    payload["rainfall_in"],
                    payload["soil_moisture_10cm"],
                    payload["soil_moisture_30cm"],
                    payload["soil_moisture_60cm"],
                    payload["soil_temp_f"],
                    payload["water_tank_pct"],
                    payload["trough_level_pct"],
                    payload["battery_voltage"],
                    payload["solar_voltage"],
                    payload["signal_strength"],
                    payload["rssi"],
                    payload["snr"],
                    payload["hop_count"],
                    payload["firmware_version"],
                    payload["notes"],
                ),
            )

    def upsert_station_status(self, status: StationStatus) -> None:
        payload = status.to_record()
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO station_status
                (station_id, last_seen, status, battery_status, signal_status, sensor_error_status, alerts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["station_id"],
                    pd.Timestamp(payload["last_seen"]).isoformat() if not pd.isna(payload["last_seen"]) else None,
                    payload["status"],
                    payload["battery_status"],
                    payload["signal_status"],
                    payload["sensor_error_status"],
                    json.dumps(payload["alerts"]),
                ),
            )

    def fetch_raw_packets(self, limit: int | None = None) -> pd.DataFrame:
        query = "SELECT * FROM raw_packets ORDER BY received_at DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        df = pd.read_sql_query(query, self.connection)
        if not df.empty:
            df["received_at"] = pd.to_datetime(df["received_at"])
            df["decoded_ok"] = df["decoded_ok"].astype(bool)
        return df

    def fetch_sensor_readings(self, limit: int | None = None) -> pd.DataFrame:
        query = "SELECT * FROM sensor_readings ORDER BY timestamp DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        df = pd.read_sql_query(query, self.connection)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.drop(columns=["id"], errors="ignore").sort_values(["station_id", "timestamp"]).reset_index(drop=True)
        return df

    def fetch_station_status(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM station_status ORDER BY station_id", self.connection)
        if not df.empty:
            df["last_seen"] = pd.to_datetime(df["last_seen"])
            df["alerts"] = df["alerts_json"].apply(json.loads)
            df = df.drop(columns=["alerts_json"])
        return df

    def close(self) -> None:
        self.connection.close()
