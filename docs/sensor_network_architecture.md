# Sensor Network Architecture

RangeIQ's sensor-network MVP is designed around a ranch base station and many remote stations.

## Flow

1. Remote station reads sensors.
2. Remote station sends a compact telemetry packet over Meshtastic/LoRa.
3. The ranch base station receives the packet through a local Meshtastic node.
4. A Python ingestion service reads packets from MQTT, serial, CSV import, or mock transport.
5. RangeIQ stores raw packets and normalized readings.
6. The dashboard surfaces station status, alerts, and network health.

## Roles

- Remote sensor station: weather, soil, water tank, trough, combined, or relay role.
- Hilltop relay: extends range and forwards traffic across rough terrain.
- Base station: Raspberry Pi or similar computer with a Meshtastic node and local storage.
- Dashboard: Streamlit interface for ranch operations.

## MVP status

The current implementation is mock-first. It includes:

- compact packet parser/encoder
- mock transport
- SQLite storage
- station status classification
- mesh health summary
- dashboard integration

Future work will connect this same architecture to real Meshtastic MQTT and serial feeds.
