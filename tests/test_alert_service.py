import pandas as pd

from ranch_ai.services.alert_service import classify_ranch_relevance, normalize_alerts


def test_alert_normalization_and_relevance_mapping():
    raw_alerts = [
        {
            "id": "demo-red-flag",
            "properties": {
                "event": "Red Flag Warning",
                "severity": "Severe",
                "urgency": "Immediate",
                "certainty": "Observed",
                "effective": "2026-04-26T10:00:00Z",
                "expires": "2026-04-26T20:00:00Z",
                "headline": "Critical fire weather conditions",
                "description": "Strong wind and low humidity.",
                "senderName": "National Weather Service",
            },
        },
        {
            "id": "demo-heat",
            "properties": {
                "event": "Heat Advisory",
                "severity": "Moderate",
                "urgency": "Expected",
                "certainty": "Likely",
                "effective": "2026-04-26T12:00:00Z",
                "expires": "2026-04-26T21:00:00Z",
                "headline": "Hot afternoon expected",
                "description": "Heat stress is possible.",
                "senderName": "National Weather Service",
            },
        },
    ]

    alerts = normalize_alerts(raw_alerts)

    assert list(alerts["event"]) == ["Red Flag Warning", "Heat Advisory"]
    assert alerts.loc[0, "relevance"] == "HIGH"
    assert bool(alerts.loc[0, "is_fire_weather"]) is True
    assert "Avoid welding" in alerts.loc[0, "operational_concern"]
    assert pd.notna(alerts.loc[0, "effective"])
    assert pd.notna(alerts.loc[0, "expires"])


def test_classify_ranch_relevance_marks_priority_alerts_high():
    assert classify_ranch_relevance({"event": "Wind Advisory"}) == "HIGH"
    assert classify_ranch_relevance({"event": "Random Weather Statement"}) == "LOW"
