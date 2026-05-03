from __future__ import annotations


FIRE_ALERT_EVENTS = {
    "Red Flag Warning",
    "Fire Weather Watch",
}

HIGH_PRIORITY_ALERT_EVENTS = {
    "Red Flag Warning",
    "Fire Weather Watch",
    "Wind Advisory",
    "High Wind Warning",
    "Excessive Heat Warning",
    "Heat Advisory",
    "Severe Thunderstorm Warning",
    "Flash Flood Warning",
    "Flood Watch",
    "Tornado Watch",
    "Tornado Warning",
    "Freeze Warning",
    "Winter Storm Warning",
}


def drought_rank(category: str | None) -> int:
    order = {
        None: 0,
        "None": 0,
        "D0": 1,
        "D1": 2,
        "D2": 3,
        "D3": 4,
        "D4": 5,
    }
    return order.get(category, 0)


def fire_risk_category(score: float) -> str:
    if score >= 85:
        return "EXTREME"
    if score >= 65:
        return "VERY HIGH"
    if score >= 45:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


def fire_risk_color(category: str) -> str:
    colors = {
        "LOW": "#557d4d",
        "MODERATE": "#a3864f",
        "HIGH": "#bf7b42",
        "VERY HIGH": "#a95334",
        "EXTREME": "#873725",
    }
    return colors.get(category, "#557d4d")


def event_priority(event: str | None) -> int:
    if not event:
        return 0
    if event == "Red Flag Warning":
        return 100
    if event == "Fire Weather Watch":
        return 90
    if event in {"Tornado Warning", "Flash Flood Warning", "Severe Thunderstorm Warning", "High Wind Warning"}:
        return 80
    if event in HIGH_PRIORITY_ALERT_EVENTS:
        return 70
    return 40
