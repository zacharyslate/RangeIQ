import copy

from ranch_ai.config import settings
from ranch_ai.services.weather_service import WeatherService, get_7day_forecast, get_current_weather, get_hourly_forecast


def test_weather_service_returns_normalized_mock_bundle():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.weather.provider = "mock"

    bundle = WeatherService(runtime_settings).load_weather_bundle(
        lat=runtime_settings.ranch.latitude,
        lon=runtime_settings.ranch.longitude,
    )

    assert bundle.mode == "mock"
    assert bundle.provider_name == "mock"
    assert bundle.current.temperature_f is not None
    assert bundle.current.weather_label
    assert len(bundle.forecast) == 7
    assert len(bundle.hourly) == 48
    assert {
        "date",
        "high_temp_f",
        "low_temp_f",
        "precip_probability_pct",
        "expected_precip_in",
        "wind_speed_mph",
        "weather_label",
    }.issubset(bundle.forecast.columns)
    assert {
        "timestamp",
        "temperature_f",
        "feels_like_f",
        "humidity_pct",
        "wind_speed_mph",
        "wind_gust_mph",
        "precip_probability_pct",
        "expected_precip_in",
        "weather_label",
    }.issubset(bundle.hourly.columns)


def test_weather_service_helper_functions_return_normalized_outputs():
    runtime_settings = copy.deepcopy(settings)
    runtime_settings.weather.provider = "mock"

    current = get_current_weather(runtime_settings.ranch.latitude, runtime_settings.ranch.longitude, app_settings=runtime_settings)
    forecast = get_7day_forecast(runtime_settings.ranch.latitude, runtime_settings.ranch.longitude, app_settings=runtime_settings)
    hourly = get_hourly_forecast(runtime_settings.ranch.latitude, runtime_settings.ranch.longitude, app_settings=runtime_settings)

    assert {"temperature_f", "humidity_pct", "wind_speed_mph", "weather_label"}.issubset(current.keys())
    assert not forecast.empty
    assert not hourly.empty
