# Deployment Notes

RangeIQ's current sensor-network stack is built to support a ranch base station model.

## Local deployment target

- Raspberry Pi or similar Linux mini-computer
- Meshtastic node connected over USB
- optional local MQTT broker
- SQLite for early deployments
- Streamlit dashboard on the same host or LAN

## Next deployment steps

- add a supervisor/service unit for ingestion
- rotate raw-packet logs
- evaluate Postgres when packet volume grows
- add backup/export for ranch historical telemetry
