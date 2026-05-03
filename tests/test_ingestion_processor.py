import copy

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.ingestion.processor import process_raw_packet
from ranch_ai.ingestion.service import SensorIngestionService
from ranch_ai.sensors.schema import SensorStation
from ranch_ai.storage.sqlite_store import SQLiteStore
from ranch_ai.telemetry.packet_schema import RawPacket


def test_process_raw_packet_returns_sensor_reading():
    raw_packet = RawPacket(
        packet_id="pkt-1",
        received_at=pd.Timestamp("2026-04-26 10:00:00"),
        source_transport="mock_transport",
        from_node="NP1",
        to_node="BASE1",
        payload_raw='{"n":"NP1","t":91.4,"h":22,"p":1007,"r":0.00,"s10":13.2,"s30":18.5,"w":73,"b":3.91}',
        rssi=-97,
        snr=7.1,
        hop_count=1,
    )
    station_lookup = {
        "NP1": SensorStation(
            station_id="NP1",
            station_name="North Pasture Soil Station",
            pasture_id="CC-001",
            station_type="soil",
            latitude=29.6,
            longitude=-103.5,
            installed_at=pd.Timestamp("2026-03-15"),
            expected_interval_minutes=60,
        )
    }

    reading, warnings = process_raw_packet(raw_packet, station_lookup=station_lookup)

    assert reading is not None
    assert reading.station_id == "NP1"
    assert raw_packet.decoded_ok is True
    assert warnings == []


def test_mock_ingestion_service_and_sqlite_store_creation(tmp_path):
    runtime = copy.deepcopy(settings)
    runtime.sensor_network.sqlite_path = str(tmp_path / "rangeiq_sensor_network.sqlite")
    runtime.sensor_network.mode = "mock"
    runtime.sensor_network.packet_limit = 120

    bundle = SensorIngestionService(runtime).load_network_bundle(mode="mock", seed=42, packet_limit=120)

    assert bundle.mode == "mock"
    assert not bundle.raw_packets.empty
    assert not bundle.readings.empty
    assert not bundle.station_status.empty
    assert (tmp_path / "rangeiq_sensor_network.sqlite").exists()

    store = SQLiteStore(runtime.sensor_network.sqlite_path)
    store.create_tables()
    assert not store.fetch_raw_packets(limit=5).empty
    store.close()
