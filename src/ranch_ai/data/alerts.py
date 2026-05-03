from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
import requests


class AlertProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def get_active_alerts(self, lat: float, lon: float) -> list[dict[str, Any]]:
        raise NotImplementedError


class MockAlertProvider(AlertProvider):
    provider_name = "mock"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_active_alerts(self, lat: float, lon: float) -> list[dict[str, Any]]:
        now = pd.Timestamp.now().floor("h")
        scenario = (now.dayofyear + int(abs(lat) * 10) + int(abs(lon) * 10) + self.seed) % 5

        if scenario == 0:
            return []

        if scenario == 1:
            return [
                _mock_alert(
                    alert_id="mock-fire-watch",
                    event="Fire Weather Watch",
                    severity="Moderate",
                    urgency="Expected",
                    certainty="Likely",
                    effective=now,
                    expires=now + pd.Timedelta(hours=18),
                    headline="Elevated fire weather is possible for ranch operations.",
                    description="Dry fuels, gusty winds, and low humidity could support rapid fire spread.",
                )
            ]

        if scenario == 2:
            return [
                _mock_alert(
                    alert_id="mock-red-flag",
                    event="Red Flag Warning",
                    severity="Severe",
                    urgency="Immediate",
                    certainty="Observed",
                    effective=now,
                    expires=now + pd.Timedelta(hours=10),
                    headline="Critical fire weather for the Baird ranch area.",
                    description="Strong winds and very low humidity can cause any new fire start to spread quickly.",
                ),
                _mock_alert(
                    alert_id="mock-wind-advisory",
                    event="Wind Advisory",
                    severity="Moderate",
                    urgency="Expected",
                    certainty="Likely",
                    effective=now,
                    expires=now + pd.Timedelta(hours=12),
                    headline="Windy conditions may impact water, fencing, and station hardware.",
                    description="Plan for difficult travel on ranch roads and higher evaporative demand on livestock water.",
                ),
            ]

        if scenario == 3:
            return [
                _mock_alert(
                    alert_id="mock-heat",
                    event="Heat Advisory",
                    severity="Moderate",
                    urgency="Expected",
                    certainty="Likely",
                    effective=now,
                    expires=now + pd.Timedelta(hours=14),
                    headline="Hot conditions expected through late afternoon.",
                    description="Heat stress can rise quickly where shade and reliable water are limited.",
                )
            ]

        return [
            _mock_alert(
                alert_id="mock-thunderstorm",
                event="Severe Thunderstorm Warning",
                severity="Severe",
                urgency="Immediate",
                certainty="Observed",
                effective=now,
                expires=now + pd.Timedelta(hours=2),
                headline="Severe thunderstorm approaching ranch operations area.",
                description="Damaging winds and lightning are possible. Check exposed equipment and station enclosures.",
            )
        ]


def _mock_alert(
    alert_id: str,
    event: str,
    severity: str,
    urgency: str,
    certainty: str,
    effective: pd.Timestamp,
    expires: pd.Timestamp,
    headline: str,
    description: str,
) -> dict[str, Any]:
    return {
        "id": alert_id,
        "properties": {
            "event": event,
            "severity": severity,
            "urgency": urgency,
            "certainty": certainty,
            "effective": effective.isoformat(),
            "expires": expires.isoformat(),
            "headline": headline,
            "description": description,
            "senderName": "Mock Alert Provider",
        },
    }


class NWSAlertProvider(AlertProvider):
    provider_name = "nws"

    def __init__(self, user_agent: str, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/geo+json"})

    def get_active_alerts(self, lat: float, lon: float) -> list[dict[str, Any]]:
        response = self.session.get(
            "https://api.weather.gov/alerts/active",
            params={"point": f"{lat:.4f},{lon:.4f}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("features", [])
