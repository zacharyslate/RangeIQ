from __future__ import annotations

from ranch_ai.transports.meshtastic_mqtt import MeshtasticMQTTClient


def main() -> None:
    client = MeshtasticMQTTClient()
    try:
        client.connect()
    except Exception as exc:
        print(f"Meshtastic MQTT ingestion is not implemented yet: {exc}")


if __name__ == "__main__":
    main()
