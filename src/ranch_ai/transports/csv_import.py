from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from ranch_ai.sensors.schema import SensorReading
from ranch_ai.telemetry.encoder import encode_compact_json
from ranch_ai.telemetry.packet_schema import RawPacket
from ranch_ai.transports.base import TransportClient


class CSVImportTransport(TransportClient):
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self._connected = False
        self._packets: list[RawPacket] = []
        self._index = 0

    def connect(self) -> None:
        df = pd.read_csv(self.csv_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        self._packets = []
        for idx, row in enumerate(df.to_dict(orient="records")):
            reading = SensorReading(
                station_id=str(row["station_id"]),
                pasture_id=str(row.get("pasture_id", "")),
                timestamp=pd.Timestamp(row["timestamp"]),
                air_temp_f=row.get("air_temp_f"),
                humidity_pct=row.get("humidity_pct"),
                pressure_hpa=row.get("pressure_hpa"),
                rainfall_in=row.get("rainfall_in"),
                soil_moisture_10cm=row.get("soil_moisture_10cm"),
                soil_moisture_30cm=row.get("soil_moisture_30cm"),
                soil_moisture_60cm=row.get("soil_moisture_60cm"),
                soil_temp_f=row.get("soil_temp_f"),
                water_tank_pct=row.get("water_tank_pct"),
                trough_level_pct=row.get("trough_level_pct"),
                battery_voltage=row.get("battery_voltage"),
                solar_voltage=row.get("solar_voltage"),
                signal_strength=row.get("signal_strength"),
                rssi=row.get("rssi"),
                snr=row.get("snr"),
                hop_count=row.get("hop_count"),
                firmware_version=str(row.get("firmware_version", "")),
                notes=str(row.get("notes", "")),
            )
            digest = hashlib.sha1(f"{reading.station_id}-{reading.timestamp.isoformat()}-{idx}".encode("utf-8")).hexdigest()[:12]
            self._packets.append(
                RawPacket(
                    packet_id=f"csv-{digest}",
                    received_at=pd.Timestamp(reading.timestamp),
                    source_transport="csv_import",
                    from_node=reading.station_id,
                    to_node="BASE1",
                    payload_raw=encode_compact_json(reading),
                    rssi=reading.rssi,
                    snr=reading.snr,
                    hop_count=reading.hop_count,
                    channel="csv-import",
                )
            )
        self._connected = True
        self._index = 0

    def disconnect(self) -> None:
        self._connected = False

    def read_packet(self) -> RawPacket | None:
        if not self._connected or self._index >= len(self._packets):
            return None
        packet = self._packets[self._index]
        self._index += 1
        return packet

    def is_connected(self) -> bool:
        return self._connected
