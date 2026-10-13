"""Operational service layer for RangeIQ Texas.

Attributes are imported lazily (PEP 562) so ``ranch_ai.services.auth_service``
can be used by the light phone-app API without loading pandas, scikit-learn
or rasterio.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS = {
    "AlertService": "ranch_ai.services.alert_service",
    "AuthError": "ranch_ai.services.auth_service",
    "AuthService": "ranch_ai.services.auth_service",
    "AuthUser": "ranch_ai.services.auth_service",
    "FireRiskAssessment": "ranch_ai.services.fire_risk_service",
    "assess_fire_risk": "ranch_ai.services.fire_risk_service",
    "PublicDataService": "ranch_ai.services.public_data_service",
    "SensorService": "ranch_ai.services.sensor_service",
    "SensorIngestionService": "ranch_ai.ingestion.service",
    "VegetationService": "ranch_ai.vegetation.vegetation_service",
    "WeatherService": "ranch_ai.services.weather_service",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value
