from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.ingestion.normalized_store import save_sensor_reading, save_station_status
from ranch_ai.ingestion.processor import process_raw_packet
from ranch_ai.ingestion.raw_store import save_raw_packet
from ranch_ai.network.alerts import build_network_alerts
from ranch_ai.network.mesh_health import build_node_health_table, summarize_mesh_health
from ranch_ai.sensors.mock import build_mock_station_registry
from ranch_ai.sensors.registry import build_station_lookup, stations_to_dataframe
from ranch_ai.sensors.status import SensorStatusThresholds, build_station_status_table
from ranch_ai.storage.sqlite_store import SQLiteStore
from ranch_ai.transports.csv_import import CSVImportTransport
from ranch_ai.transports.mock_transport import MockTransportClient


@dataclass
class SensorNetworkBundle:
    stations: pd.DataFrame
    raw_packets: pd.DataFrame
    readings: pd.DataFrame
    latest_readings: pd.DataFrame
    station_status: pd.DataFrame
    network_health: pd.DataFrame
    network_summary: dict[str, Any]
    alerts: pd.DataFrame
    mode: str
    source_transport: str
    loaded_at: pd.Timestamp
    store_path: str
    source_message: str


class SensorIngestionService:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings

    def _status_thresholds(self) -> SensorStatusThresholds:
        return SensorStatusThresholds(
            expected_interval_minutes=self.settings.sensor_network.expected_interval_minutes,
            stale_after_minutes=self.settings.sensor_network.stale_after_minutes,
            offline_after_minutes=self.settings.sensor_network.offline_after_minutes,
            low_battery_voltage=self.settings.thresholds.low_battery_voltage,
            low_signal_rssi=self.settings.thresholds.low_signal_rssi,
            low_water_tank_pct=self.settings.thresholds.low_water_tank_pct,
        )

    def _build_stations(self):
        return build_mock_station_registry(
            base_lat=self.settings.ranch.latitude,
            base_lon=self.settings.ranch.longitude,
            pasture_id="CC-001",
            expected_interval_minutes=self.settings.sensor_network.expected_interval_minutes,
        )

    def _build_transport(self, mode: str, seed: int):
        if mode == "csv":
            csv_path = self.settings.sensor_data_dir / "sensor_readings.example.csv"
            return CSVImportTransport(csv_path), "csv_import", f"Loaded telemetry from {csv_path}"
        if mode in {"meshtastic_mqtt", "meshtastic_serial"}:
            return MockTransportClient(seed=seed, base_lat=self.settings.ranch.latitude, base_lon=self.settings.ranch.longitude), "mock_transport", "Live Meshtastic transport is not implemented yet; using mock telemetry."
        return MockTransportClient(seed=seed, base_lat=self.settings.ranch.latitude, base_lon=self.settings.ranch.longitude), "mock_transport", "Using mock Meshtastic/LoRa telemetry."

    def load_network_bundle(self, mode: str | None = None, seed: int | None = None, packet_limit: int | None = None) -> SensorNetworkBundle:
        active_mode = (mode or self.settings.sensor_network.mode).lower()
        seed_value = int(seed if seed is not None else self.settings.random_seed)
        loaded_at = pd.Timestamp.now().floor("min")
        stations = self._build_stations()
        station_lookup = build_station_lookup(stations)
        store = SQLiteStore(self.settings.sensor_network.sqlite_path)
        store.create_tables()
        store.reset()

        transport, transport_name, source_message = self._build_transport(active_mode, seed_value)
        transport.connect()
        max_packets = int(packet_limit or self.settings.sensor_network.packet_limit)

        for _ in range(max_packets):
            raw_packet = transport.read_packet()
            if raw_packet is None:
                break
            reading, _warnings = process_raw_packet(raw_packet, station_lookup=station_lookup)
            save_raw_packet(store, raw_packet)
            if reading is not None:
                save_sensor_reading(store, reading)
        transport.disconnect()

        raw_packets_df = store.fetch_raw_packets(limit=max_packets).sort_values("received_at").reset_index(drop=True)
        readings_df = store.fetch_sensor_readings(limit=max_packets)
        latest_readings_df = (
            readings_df.sort_values("timestamp").groupby("station_id", as_index=False).tail(1).reset_index(drop=True)
            if not readings_df.empty
            else pd.DataFrame()
        )

        status_objects = build_station_status_table(stations, readings_df, now=loaded_at, thresholds=self._status_thresholds())
        for status in status_objects:
            save_station_status(store, status)
        status_df = store.fetch_station_status()

        stations_df = stations_to_dataframe(stations)
        network_health_df = build_node_health_table(raw_packets_df, status_df, stations_df, low_signal_rssi=self.settings.thresholds.low_signal_rssi)
        network_summary = summarize_mesh_health(raw_packets_df, status_df, stations_df, low_signal_rssi=self.settings.thresholds.low_signal_rssi)
        alerts_df = build_network_alerts(status_df, network_health_df)
        store.close()

        return SensorNetworkBundle(
            stations=stations_df,
            raw_packets=raw_packets_df,
            readings=readings_df,
            latest_readings=latest_readings_df,
            station_status=status_df,
            network_health=network_health_df,
            network_summary=network_summary,
            alerts=alerts_df,
            mode=active_mode,
            source_transport=transport_name,
            loaded_at=loaded_at,
            store_path=str(self.settings.sensor_network.sqlite_path),
            source_message=source_message,
        )
