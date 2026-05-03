from __future__ import annotations

from ranch_ai.transports.meshtastic_serial import MeshtasticSerialClient


def main() -> None:
    client = MeshtasticSerialClient()
    try:
        client.connect()
    except Exception as exc:
        print(f"Meshtastic serial ingestion is not implemented yet: {exc}")


if __name__ == "__main__":
    main()
