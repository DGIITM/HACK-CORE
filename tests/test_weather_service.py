"""M3's weather integration: Open-Meteo (free, no key) with an honest
fallback for unknown districts and unreachable hosts. The unreachable
case is forced deterministically by pointing at a bad host/URL rather
than relying on flaky "disconnect the network" tricks.
"""
from app.services import weather_service


def test_known_district_returns_a_real_forecast():
    forecast = weather_service.get_forecast("Ludhiana")
    assert forecast.is_fallback is False
    assert forecast.rain_mm is not None
    assert isinstance(forecast.summary, str) and forecast.summary


def test_unknown_district_returns_honest_fallback_not_a_guessed_location():
    forecast = weather_service.get_forecast("Nowhere District")
    assert forecast.is_fallback is True
    assert forecast.rain_mm is None
    assert "unavailable" in forecast.summary


def test_unreachable_host_falls_back_honestly():
    forecast = weather_service.get_forecast(
        "Ludhiana", base_url="https://invalid.host.that.does.not.exist.example/forecast", timeout=2
    )
    assert forecast.is_fallback is True
    assert forecast.rain_mm is None


def test_malformed_response_falls_back_honestly():
    """Simulates Open-Meteo being reachable but returning something we
    don't understand — should degrade gracefully, not crash."""
    forecast = weather_service.get_forecast("Ludhiana", base_url="https://api.open-meteo.com/v1/nonexistent-endpoint")
    assert forecast.is_fallback is True
