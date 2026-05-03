import copy

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.services.fire_risk_service import assess_fire_risk


def test_fire_risk_service_escalates_with_red_flag_conditions():
    runtime_settings = copy.deepcopy(settings)
    current_weather = {
        "temperature_f": 98.0,
        "humidity_pct": 14.0,
        "wind_speed_mph": 28.0,
        "wind_gust_mph": 41.0,
        "rainfall_expected_today_in": 0.0,
    }
    alerts_df = pd.DataFrame(
        [
            {
                "event": "Red Flag Warning",
                "severity": "Severe",
                "relevance": "HIGH",
            }
        ]
    )
    latest_snapshot = pd.DataFrame(
        [
            {"rainfall_7d": 1.0, "drought_category": "D2", "ndvi_anomaly": -0.15},
            {"rainfall_7d": 1.5, "drought_category": "D1", "ndvi_anomaly": -0.12},
        ]
    )
    sensor_status_df = pd.DataFrame(
        [
            {"station_id": "ST-P-101", "soil_moisture_30cm": 9.5, "water_tank_pct": 18.0, "status": "ONLINE"},
            {"station_id": "ST-P-102", "soil_moisture_30cm": 11.0, "water_tank_pct": 45.0, "status": "STALE"},
        ]
    )
    sensor_readings_df = pd.DataFrame(
        [
            {"station_id": "ST-P-101", "timestamp": pd.Timestamp.now() - pd.Timedelta(days=3), "rainfall_in": 0.0},
            {"station_id": "ST-P-102", "timestamp": pd.Timestamp.now() - pd.Timedelta(days=5), "rainfall_in": 0.0},
        ]
    )

    assessment = assess_fire_risk(
        current_weather=current_weather,
        alerts_df=alerts_df,
        latest_snapshot=latest_snapshot,
        sensor_status_df=sensor_status_df,
        sensor_readings_df=sensor_readings_df,
        app_settings=runtime_settings,
    )

    assert assessment.score >= 85
    assert assessment.category == "EXTREME"
    assert assessment.weather_inputs["has_fire_alert"] is True
    assert any("Avoid welding" in action for action in assessment.recommended_actions)
