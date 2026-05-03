# Telemetry Package

This package handles compact payload formats for RangeIQ ranch stations.

Supported MVP packet styles:

- compact JSON
- pipe-delimited text

The packet parser, encoder, and decoder are intentionally lightweight so future Meshtastic, MQTT, serial, LoRaWAN, cellular, or Wi-Fi ingestion layers can reuse the same normalized packet contract.
