from __future__ import annotations

from ranch_ai.ingestion.service import SensorIngestionService


def main() -> None:
    bundle = SensorIngestionService().load_network_bundle(mode="mock")
    print("RangeIQ mock sensor ingestion complete.")
    print(bundle.station_status[["station_id", "status", "battery_status", "signal_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
