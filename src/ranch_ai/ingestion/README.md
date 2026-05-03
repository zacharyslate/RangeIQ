# Ingestion Package

This package turns raw telemetry packets into normalized sensor readings for RangeIQ.

Current MVP flow:

1. choose a transport
2. read mock or CSV-backed packets
3. parse and validate them
4. store raw packets and normalized readings
5. update station status and mesh health summaries

The real Meshtastic MQTT and serial transports are intentionally left as placeholders for a later hardware-connected phase.
