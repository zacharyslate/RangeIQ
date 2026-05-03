from __future__ import annotations

from ranch_ai.config import settings
from ranch_ai.storage.sqlite_store import SQLiteStore


def main() -> None:
    store = SQLiteStore(settings.sensor_network.sqlite_path)
    store.create_tables()
    raw_packets = store.fetch_raw_packets(limit=10)
    readings = store.fetch_sensor_readings(limit=10)
    print("Latest raw packets")
    print(raw_packets.to_string(index=False) if not raw_packets.empty else "No packets yet.")
    print()
    print("Latest sensor readings")
    print(readings.to_string(index=False) if not readings.empty else "No readings yet.")
    store.close()


if __name__ == "__main__":
    main()
