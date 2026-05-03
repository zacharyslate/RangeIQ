from __future__ import annotations

from pathlib import Path

from ranch_ai.data_sources.land.nass_quickstats import NASSQuickStatsDataSource
from ranch_ai.data_sources.registry import SourceRegistry
from ranch_ai.data_sources.water.usgs_water import USGSWaterDataSource
from ranch_ai.data_sources.weather.nws import NWSDataSource
from ranch_ai.data_sources.weather.open_meteo import OpenMeteoDataSource


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_registry_health_check_reports_policy_flags(tmp_path: Path):
    config_path = tmp_path / "api_sources.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_sources:",
                "  open_meteo:",
                "    enabled: true",
                "    access_level: no_key_free_noncommercial",
                "    commercial_safe: false",
                "    warning: Free tier is development/research only.",
                "  nasa_firms:",
                "    enabled: false",
                "    key_env: NASA_FIRMS_MAP_KEY",
            ]
        ),
        encoding="utf-8",
    )

    registry = SourceRegistry(config_path=config_path)
    statuses = {status["name"]: status for status in registry.health_check().statuses}

    assert statuses["open_meteo"]["enabled"] is True
    assert statuses["open_meteo"]["commercial_safe"] is False
    assert "development/research" in (statuses["open_meteo"]["warning"] or "")
    assert statuses["nasa_firms"]["enabled"] is False
    assert "NASA_FIRMS_MAP_KEY" in statuses["nasa_firms"]["required_env"]


def test_open_meteo_provider_normalizes_response(monkeypatch):
    def fake_request(self, method, url, params=None, headers=None, timeout=None):
        assert "open-meteo.com" in url
        return DummyResponse(
            {
                "timezone": "America/Chicago",
                "generationtime_ms": 1.2,
                "current": {
                    "time": "2026-04-27T12:00",
                    "temperature_2m": 81.2,
                    "apparent_temperature": 83.5,
                    "relative_humidity_2m": 24,
                    "precipitation": 0.0,
                    "precipitation_probability": 5,
                    "wind_speed_10m": 18.4,
                    "wind_gusts_10m": 27.0,
                    "wind_direction_10m": 225,
                    "soil_moisture_0_to_1cm": 0.14,
                    "soil_temperature_0cm": 74.2,
                },
                "daily": {
                    "time": ["2026-04-27", "2026-04-28"],
                    "weather_code": [0, 3],
                    "temperature_2m_max": [88.0, 86.0],
                    "temperature_2m_min": [58.0, 60.0],
                    "precipitation_sum": [0.0, 0.1],
                    "precipitation_probability_max": [5, 35],
                    "wind_speed_10m_max": [22.0, 18.0],
                    "wind_gusts_10m_max": [31.0, 25.0],
                },
                "hourly": {
                    "time": ["2026-04-27T12:00", "2026-04-27T13:00"],
                    "temperature_2m": [81.2, 82.1],
                    "relative_humidity_2m": [24, 22],
                    "precipitation_probability": [5, 4],
                    "precipitation": [0.0, 0.0],
                    "wind_speed_10m": [18.4, 19.1],
                    "soil_moisture_0_to_1cm": [0.14, 0.14],
                    "soil_temperature_0cm": [74.2, 74.8],
                    "evapotranspiration": [0.01, 0.02],
                },
            }
        )

    monkeypatch.setattr("requests.sessions.Session.request", fake_request)

    provider = OpenMeteoDataSource(config={"enabled": True})
    payload = provider.fetch_point(29.60, -103.50)

    assert payload["source"] == "open_meteo"
    assert payload["data"]["current"]["temperature_f"] == 81.2
    assert len(payload["data"]["daily"]) == 2
    assert "development" in payload["warnings"][0].lower()


def test_nws_provider_normalizes_response(monkeypatch):
    def fake_request(self, method, url, params=None, headers=None, timeout=None):
        if "api.weather.gov/points/" in url:
            return DummyResponse(
                {
                    "properties": {
                        "gridId": "MAF",
                        "forecast": "https://api.weather.gov/gridpoints/MAF/1,2/forecast",
                        "forecastHourly": "https://api.weather.gov/gridpoints/MAF/1,2/forecast/hourly",
                        "observationStations": "https://api.weather.gov/gridpoints/MAF/1,2/stations",
                    }
                }
            )
        if url.endswith("/stations"):
            return DummyResponse(
                {
                    "features": [
                        {
                            "id": "https://api.weather.gov/stations/KALP",
                            "properties": {"name": "Alpine", "stationIdentifier": "KALP"},
                        }
                    ]
                }
            )
        if url.endswith("/observations/latest"):
            return DummyResponse(
                {
                    "properties": {
                        "timestamp": "2026-04-27T16:00:00+00:00",
                        "temperature": {"value": 25, "unitCode": "wmoUnit:degC"},
                        "relativeHumidity": {"value": 21, "unitCode": "wmoUnit:percent"},
                        "windSpeed": {"value": 8, "unitCode": "wmoUnit:m_s-1"},
                        "windGust": {"value": 12, "unitCode": "wmoUnit:m_s-1"},
                        "windDirection": {"value": 230, "unitCode": "wmoUnit:degree_(angle)"},
                        "precipitationLastHour": {"value": 0, "unitCode": "wmoUnit:mm"},
                        "textDescription": "Sunny",
                    }
                }
            )
        if url.endswith("/forecast") and not url.endswith("/hourly"):
            return DummyResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "startTime": "2026-04-27T12:00:00-05:00",
                                "temperature": 85,
                                "temperatureUnit": "F",
                                "windSpeed": "15 to 20 mph",
                                "windDirection": "SW",
                                "probabilityOfPrecipitation": {"value": 15},
                                "shortForecast": "Sunny",
                            }
                        ]
                    }
                }
            )
        if url.endswith("/forecast/hourly"):
            return DummyResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-04-27T12:00:00-05:00",
                                "temperature": 84,
                                "windSpeed": "15 mph",
                                "windDirection": "SW",
                                "probabilityOfPrecipitation": {"value": 10},
                                "shortForecast": "Sunny",
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("requests.sessions.Session.request", fake_request)

    provider = NWSDataSource(config={"enabled": True, "user_agent": "RangeIQ test"})
    payload = provider.fetch_point(29.60, -103.50)

    assert payload["source"] == "nws"
    assert payload["data"]["current"]["station_id"] == "KALP"
    assert round(payload["data"]["current"]["temperature_f"], 1) == 77.0
    assert payload["data"]["daily"][0]["wind_speed_mph"] == 17.5


def test_usgs_water_provider_normalizes_nearest_station(monkeypatch):
    def fake_request(self, method, url, params=None, headers=None, timeout=None):
        if "monitoring-locations/items" in url:
            return DummyResponse(
                {
                    "features": [
                        {
                            "id": "USGS-08449000",
                            "geometry": {"type": "Point", "coordinates": [-103.49, 29.61]},
                            "properties": {
                                "monitoring_location_id": "USGS-08449000",
                                "monitoring_location_name": "Rio Grande near Alpine",
                                "site_type": "Stream",
                                "state_name": "Texas",
                                "county_name": "Brewster",
                            },
                        }
                    ]
                }
            )
        if "latest-continuous/items" in url:
            return DummyResponse(
                {
                    "features": [
                        {
                            "properties": {
                                "time": "2026-04-27T15:45:00+00:00",
                                "parameter_code": "00060",
                                "value": "4.12",
                                "unit_of_measure": "ft3/s",
                                "approvals_status": ["Approved"],
                            }
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("requests.sessions.Session.request", fake_request)

    provider = USGSWaterDataSource(config={"enabled": True})
    payload = provider.fetch_point(29.60, -103.50)

    assert payload["source"] == "usgs_water"
    assert payload["data"]["nearest_station"]["monitoring_location_id"] == "USGS-08449000"
    assert payload["data"]["latest_observations"][0]["parameter_code"] == "00060"


def test_nass_quickstats_missing_key_is_nonfatal():
    provider = NASSQuickStatsDataSource(config={"enabled": True, "key_env": "USDA_NASS_API_KEY"})
    payload = provider.fetch_point(29.60, -103.50, state_alpha="TX", county_name="BREWSTER")

    assert payload["source"] == "nass_quickstats"
    assert payload["data"] == {}
    assert "USDA_NASS_API_KEY" in payload["warnings"][0]
