"""Open-Meteo weather forecast for M3 Risk Intelligence — free, no API
key required (CLAUDE.md: no paid weather API has been set up anywhere
in this project). This is the first module whose real external
dependency is actually reachable from this dev sandbox without GCP
credentials — verified working with a live call before wiring it in.

Falls back to a clearly-labeled neutral forecast if Open-Meteo is
unreachable, or if a district has no known coordinates — same
fallback-honesty pattern as every other module, even though this one
usually succeeds here.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 5  # matches CLAUDE.md's own example wording ("no heavy rain expected for 5 days")
RAIN_THRESHOLD_MM = 15.0  # judgment call: a moderate-to-heavy accumulated total, not a single downpour

# Approximate district-headquarters coordinates for the 20 districts M2
# has soil/pest data for — public geographic knowledge, not a paid
# geocoding service. Precision to a few km is more than enough for a
# multi-day rain-risk signal.
DISTRICT_COORDINATES = {
    "Ludhiana": (30.9010, 75.8573),
    "Amritsar": (31.6340, 74.8723),
    "Jalandhar": (31.3260, 75.5762),
    "Patiala": (30.3398, 76.3869),
    "Bathinda": (30.2110, 74.9455),
    "Sangrur": (30.2458, 75.8421),
    "Ferozepur": (30.9331, 74.6225),
    "Moga": (30.8158, 75.1711),
    "Fatehgarh Sahib": (30.6446, 76.3900),
    "Gurdaspur": (32.0410, 75.4053),
    "Hoshiarpur": (31.5324, 75.9119),
    "Kapurthala": (31.3800, 75.3805),
    "Mansa": (29.9990, 75.3930),
    "Muktsar": (30.4762, 74.5161),
    "Rupnagar": (30.9680, 76.5270),
    "SAS Nagar Mohali": (30.7046, 76.7179),
    "Faridkot": (30.6764, 74.7553),
    "Fazilka": (30.4030, 74.0263),
    "Barnala": (30.3746, 75.5477),
    "Tarn Taran": (31.4520, 74.9264),
    "Pathankot": (32.2643, 75.6421),
}

FALLBACK_SUMMARY = "weather forecast unavailable right now — assuming average conditions rather than guessing"


@dataclass
class WeatherForecast:
    summary: str
    rain_mm: Optional[float]  # None only when is_fallback is True
    is_fallback: bool


def _fetch(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def get_forecast(district: str, base_url: str = OPEN_METEO_URL, timeout: float = 6.0) -> WeatherForecast:
    coordinates = DISTRICT_COORDINATES.get(district)
    if coordinates is None:
        # Shouldn't normally happen — risk_context.py only calls this for
        # districts M2 already confirmed it has soil data for, and that
        # list was built to match this one — but never assume a
        # coordinate for a place we don't actually have one for.
        logger.warning("No coordinates known for district %r — returning neutral weather fallback.", district)
        return WeatherForecast(summary=FALLBACK_SUMMARY, rain_mm=None, is_fallback=True)

    lat, lon = coordinates
    url = (
        f"{base_url}?latitude={lat}&longitude={lon}"
        f"&daily=precipitation_sum&forecast_days={FORECAST_DAYS}&timezone=auto"
    )
    try:
        data = _fetch(url, timeout)
        rain_mm = sum(data["daily"]["precipitation_sum"])
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        logger.warning("Open-Meteo forecast unavailable for %r (%s) — using neutral fallback.", district, exc)
        return WeatherForecast(summary=FALLBACK_SUMMARY, rain_mm=None, is_fallback=True)

    if rain_mm > RAIN_THRESHOLD_MM:
        summary = f"heavy rain expected over the next {FORECAST_DAYS} days ({rain_mm:.0f}mm total)"
    elif rain_mm > 2:
        summary = f"light rain expected over the next {FORECAST_DAYS} days ({rain_mm:.0f}mm total)"
    else:
        summary = f"no heavy rain expected for {FORECAST_DAYS} days"

    return WeatherForecast(summary=summary, rain_mm=rain_mm, is_fallback=False)
