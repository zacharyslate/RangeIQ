import pandas as pd

from ranch_ai.network.mesh_health import build_node_health_table, summarize_mesh_health


def test_mesh_health_summary_flags_offline_and_low_signal_nodes():
    raw_packets_df = pd.DataFrame(
        [
            {"from_node": "NP1", "received_at": pd.Timestamp("2026-04-26 10:00:00"), "rssi": -94, "snr": 8.0},
            {"from_node": "RLY1", "received_at": pd.Timestamp("2026-04-26 10:05:00"), "rssi": -119, "snr": 2.0},
        ]
    )
    status_df = pd.DataFrame(
        [
            {"station_id": "NP1", "status": "ONLINE", "battery_status": "OK", "signal_status": "OK", "sensor_error_status": "OK", "alerts": []},
            {"station_id": "RLY1", "status": "OFFLINE", "battery_status": "OK", "signal_status": "LOW_SIGNAL", "sensor_error_status": "OK", "alerts": ["OFFLINE", "LOW_SIGNAL"]},
        ]
    )
    stations_df = pd.DataFrame(
        [
            {"station_id": "NP1", "station_name": "North Pasture Soil Station", "station_type": "soil", "pasture_id": "CC-001"},
            {"station_id": "RLY1", "station_name": "Hilltop Relay", "station_type": "relay", "pasture_id": "CC-001"},
        ]
    )

    health_df = build_node_health_table(raw_packets_df, status_df, stations_df, low_signal_rssi=-115)
    summary = summarize_mesh_health(raw_packets_df, status_df, stations_df, low_signal_rssi=-115)

    assert "avg_rssi" in health_df.columns
    assert summary["relay_nodes"] == ["RLY1"]
    assert "RLY1" in summary["offline_nodes"]
    assert "RLY1" in summary["low_signal_nodes"]
