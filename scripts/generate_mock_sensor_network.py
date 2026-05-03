from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.network.mesh_health import build_node_health_table
from ranch_ai.sensors.mock import build_mock_station_registry, generate_mock_sensor_readings, sensor_readings_to_dataframe
from ranch_ai.sensors.registry import stations_to_dataframe
from ranch_ai.sensors.status import SensorStatusThresholds, build_station_status_table
from ranch_ai.telemetry.parser import parse_packet
from ranch_ai.transports.mock_transport import MockTransportClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_station_registry_yaml(stations_df: pd.DataFrame, destination: Path) -> None:
    lines = ["stations:"]
    for row in stations_df.to_dict(orient="records"):
        safe_notes = str(row["notes"]).replace('"', "'")
        lines.extend(
            [
                f"  {row['station_id']}:",
                f"    station_name: \"{row['station_name']}\"",
                f"    pasture_id: \"{row['pasture_id']}\"",
                f"    station_type: \"{row['station_type']}\"",
                f"    latitude: {row['latitude']}",
                f"    longitude: {row['longitude']}",
                f"    installed_at: \"{pd.Timestamp(row['installed_at']).isoformat()}\"",
                f"    expected_interval_minutes: {row['expected_interval_minutes']}",
                f"    sensors: \"{row['sensors']}\"",
                f"    active: {str(bool(row['active'])).lower()}",
                f"    notes: \"{safe_notes}\"",
            ]
        )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_node_registry_yaml(stations_df: pd.DataFrame, destination: Path) -> None:
    lines = ["nodes:"]
    for row in stations_df.to_dict(orient="records"):
        lines.extend(
            [
                f"  {row['station_id']}:",
                f"    station_id: \"{row['station_id']}\"",
                f"    role: \"{row['station_type']}\"",
                f"    pasture_id: \"{row['pasture_id']}\"",
                f"    notes: \"Mock node definition for RangeIQ demo.\"",
            ]
        )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    sensor_dir = PROJECT_ROOT / "data" / "sensors"
    telemetry_dir = PROJECT_ROOT / "data" / "telemetry"
    network_dir = PROJECT_ROOT / "data" / "network"
    for directory in [sensor_dir, telemetry_dir, network_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    stations = build_mock_station_registry(
        base_lat=settings.ranch.latitude,
        base_lon=settings.ranch.longitude,
        pasture_id="CC-001",
        expected_interval_minutes=settings.sensor_network.expected_interval_minutes,
    )
    readings = generate_mock_sensor_readings(stations, seed=settings.random_seed, days=7)
    stations_df = stations_to_dataframe(stations)
    readings_df = sensor_readings_to_dataframe(readings)

    status_objects = build_station_status_table(
        stations,
        readings_df,
        now=readings_df["timestamp"].max() + pd.Timedelta(hours=16),
        thresholds=SensorStatusThresholds(
            expected_interval_minutes=settings.sensor_network.expected_interval_minutes,
            stale_after_minutes=settings.sensor_network.stale_after_minutes,
            offline_after_minutes=settings.sensor_network.offline_after_minutes,
            low_battery_voltage=settings.thresholds.low_battery_voltage,
            low_signal_rssi=settings.thresholds.low_signal_rssi,
            low_water_tank_pct=settings.thresholds.low_water_tank_pct,
        ),
    )
    status_df = pd.DataFrame([status.to_record() for status in status_objects])

    transport = MockTransportClient(stations=stations, readings=readings, seed=settings.random_seed, base_lat=settings.ranch.latitude, base_lon=settings.ranch.longitude)
    transport.connect()
    raw_packets = []
    for _ in range(48):
        packet = transport.read_packet()
        if packet is None:
            break
        raw_packets.append(packet.to_record())
    transport.disconnect()
    raw_packets_df = pd.DataFrame(raw_packets)
    if not raw_packets_df.empty:
        raw_packets_df["received_at"] = pd.to_datetime(raw_packets_df["received_at"])

    network_health_df = build_node_health_table(raw_packets_df, status_df, stations_df, low_signal_rssi=settings.thresholds.low_signal_rssi)
    decoded_examples = []
    for record in raw_packets[:6]:
        decoded = parse_packet(record["payload_raw"]).to_record()
        if pd.isna(decoded["timestamp"]):
            decoded["timestamp"] = pd.Timestamp(record["received_at"])
        decoded_examples.append(decoded)

    stations_df.to_csv(sensor_dir / "sensor_stations.example.csv", index=False)
    readings_df.to_csv(sensor_dir / "sensor_readings.example.csv", index=False)
    readings_df.to_csv(sensor_dir / "sensor_readings.csv", index=False)

    with (sensor_dir / "raw_packets.example.jsonl").open("w", encoding="utf-8") as handle:
        for row in raw_packets:
            record = row.copy()
            record["received_at"] = pd.Timestamp(record["received_at"]).isoformat()
            handle.write(json.dumps(record) + "\n")

    write_station_registry_yaml(stations_df, sensor_dir / "station_registry.example.yaml")

    (telemetry_dir / "compact_packet_examples.txt").write_text(
        "\n".join([raw_packets[idx]["payload_raw"] for idx in range(min(8, len(raw_packets)))]),
        encoding="utf-8",
    )
    (telemetry_dir / "decoded_packet_examples.json").write_text(
        json.dumps(
            [{**example, "timestamp": pd.Timestamp(example["timestamp"]).isoformat()} for example in decoded_examples],
            indent=2,
        ),
        encoding="utf-8",
    )

    write_node_registry_yaml(stations_df, network_dir / "node_registry.example.yaml")
    network_health_df.to_csv(network_dir / "mesh_health.example.csv", index=False)

    print("Mock sensor network example files written.")


if __name__ == "__main__":
    main()
