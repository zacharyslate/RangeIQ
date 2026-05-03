from __future__ import annotations

from typing import Any

import pandas as pd

from ranch_ai.config import Settings, settings
from ranch_ai.data.alerts import MockAlertProvider, NWSAlertProvider
from ranch_ai.models.alert_schema import AlertBundle
from ranch_ai.optimization.risk_rules import FIRE_ALERT_EVENTS, HIGH_PRIORITY_ALERT_EVENTS, event_priority


ALERT_COLUMNS = [
    "alert_id",
    "event",
    "severity",
    "urgency",
    "certainty",
    "effective",
    "expires",
    "headline",
    "description",
    "source",
    "relevance",
    "operational_concern",
    "highlight_level",
    "is_fire_weather",
]


def _provider_from_name(provider_name: str, app_settings: Settings):
    active = provider_name.lower()
    if active == "nws":
        return NWSAlertProvider(
            user_agent=app_settings.weather.user_agent,
            timeout_seconds=app_settings.alerts.timeout_seconds,
        )
    return MockAlertProvider(seed=app_settings.random_seed)


def classify_ranch_relevance(alert: dict[str, Any]) -> str:
    event = str(alert.get("event") or "").strip()
    if event in FIRE_ALERT_EVENTS or event in HIGH_PRIORITY_ALERT_EVENTS:
        return "HIGH"
    if "Watch" in event or "Advisory" in event:
        return "MEDIUM"
    return "LOW"


def interpret_alert(alert: dict[str, Any]) -> str:
    event = str(alert.get("event") or "").strip()
    if event in {"Red Flag Warning", "Fire Weather Watch"}:
        return "Avoid welding, burning, or spark-generating work."
    if event in {"Heat Advisory", "Excessive Heat Warning"}:
        return "Check water availability and heat-stress pastures."
    if event in {"Severe Thunderstorm Warning", "High Wind Warning", "Wind Advisory"}:
        return "Inspect sensor stations and solar battery status before severe weather."
    if event in {"Flash Flood Warning", "Flood Watch"}:
        return "Check crossings, low-water routes, and remote tank access."
    if event in {"Freeze Warning", "Winter Storm Warning"}:
        return "Protect exposed plumbing, trough hardware, and vulnerable livestock groups."
    if event in {"Tornado Watch", "Tornado Warning"}:
        return "Move people and equipment to shelter and avoid exposed draws."
    return "Review current ranch operations and monitor official updates."


def _highlight_level(event: str, severity: str) -> str:
    if event == "Red Flag Warning":
        return "critical"
    if event == "Fire Weather Watch":
        return "warning"
    if severity in {"Extreme", "Severe"}:
        return "critical"
    if severity in {"Moderate"}:
        return "warning"
    return "info"


def normalize_alerts(raw_alerts: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw_alert in raw_alerts:
        properties = raw_alert.get("properties", raw_alert)
        event = str(properties.get("event") or properties.get("headline") or "Alert").strip()
        normalized = {
            "alert_id": raw_alert.get("id") or properties.get("id") or event.lower().replace(" ", "-"),
            "event": event,
            "severity": properties.get("severity") or "Unknown",
            "urgency": properties.get("urgency") or "Unknown",
            "certainty": properties.get("certainty") or "Unknown",
            "effective": pd.to_datetime(properties.get("effective") or properties.get("onset") or properties.get("sent")),
            "expires": pd.to_datetime(properties.get("expires") or properties.get("ends")),
            "headline": properties.get("headline") or event,
            "description": properties.get("description") or properties.get("instruction") or "",
            "source": properties.get("senderName") or raw_alert.get("source") or "Alert provider",
        }
        normalized["relevance"] = classify_ranch_relevance(normalized)
        normalized["operational_concern"] = interpret_alert(normalized)
        normalized["highlight_level"] = _highlight_level(normalized["event"], str(normalized["severity"]))
        normalized["is_fire_weather"] = normalized["event"] in FIRE_ALERT_EVENTS
        rows.append(normalized)

    if not rows:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    alerts = pd.DataFrame(rows)
    alerts["priority_rank"] = alerts["event"].apply(event_priority)
    alerts = alerts.sort_values(
        ["priority_rank", "effective", "severity", "event"],
        ascending=[False, False, True, True],
    ).drop(columns="priority_rank")
    return alerts[ALERT_COLUMNS].reset_index(drop=True)


def get_active_alerts(lat: float, lon: float, provider: str | None = None, app_settings: Settings = settings) -> pd.DataFrame:
    service = AlertService(app_settings=app_settings)
    return service.load_alert_bundle(lat=lat, lon=lon, provider=provider).alerts


class AlertService:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings

    def load_alert_bundle(
        self,
        lat: float,
        lon: float,
        provider: str | None = None,
    ) -> AlertBundle:
        provider_name = (provider or self.settings.alerts.provider).lower()
        active_provider = _provider_from_name(provider_name, self.settings)
        loaded_at = pd.Timestamp.now()

        try:
            alerts = normalize_alerts(active_provider.get_active_alerts(lat, lon))
            mode = "real" if provider_name == "nws" else "mock"
            source_message = f"Using {active_provider.provider_name} alerts provider."
        except Exception:
            fallback_provider = MockAlertProvider(seed=self.settings.random_seed)
            alerts = normalize_alerts(fallback_provider.get_active_alerts(lat, lon))
            mode = "fallback-mock" if provider_name != "mock" else "mock"
            source_message = f"{provider_name} alerts provider unavailable; using mock alerts."
            active_provider = fallback_provider

        return AlertBundle(
            alerts=alerts,
            provider_name=active_provider.provider_name,
            mode=mode,
            source_message=source_message,
            loaded_at=loaded_at,
        )
