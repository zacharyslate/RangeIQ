from ranch_ai.transports.mock_transport import MockTransportClient


def test_mock_transport_reads_packets():
    transport = MockTransportClient(seed=42)
    transport.connect()
    packet = transport.read_packet()
    transport.disconnect()

    assert packet is not None
    assert packet.source_transport == "mock_transport"
    assert packet.from_node in {"NP1", "SP1", "WT1", "WX1", "RLY1"}
    assert packet.payload_raw
