"""Weather windows for M3 environmental assessment.

The bundled ERA5T/Meteoblue file is useful for reproducible historical/demo
references, but must never be presented as a live forecast.  Calls without a
reference date therefore use Open-Meteo; calls with one use the bundled data.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

FORECAST_DAYS = 5
RAIN_CAUTION_MM = 15.0  # Original M3's documented five-day wash-off rule.
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

DISTRICT_COORDINATES = {
    "Ludhiana": (30.9010, 75.8573), "Bathinda": (30.2110, 74.9455),
    "Ropar": (30.9680, 76.5270), "Rupnagar": (30.9680, 76.5270),
    "Amritsar": (31.6340, 74.8723), "Jalandhar": (31.3260, 75.5762),
    "Patiala": (30.3398, 76.3860), "Sangrur": (30.2458, 75.8423),
    "Ferozepur": (30.9331, 74.6225), "Moga": (30.8158, 75.1711),
    "Fatehgarh Sahib": (30.6446, 76.3900), "Gurdaspur": (32.0410, 75.4053),
    "Hoshiarpur": (31.5320, 75.9120), "Kapurthala": (31.3800, 75.3800),
    "Mansa": (29.9990, 75.3930), "Muktsar": (30.4760, 74.5160),
    "SAS Nagar Mohali": (30.7040, 76.7170), "Faridkot": (30.6760, 74.7580),
    "Fazilka": (30.4030, 74.0280), "Barnala": (30.3810, 75.5460),
    "Tarn Taran": (31.4520, 74.9270), "Pathankot": (32.2640, 75.6420),
}

FALLBACK_SUMMARY = "current weather forecast unavailable"
_WEATHER_CACHE: Dict[str, Dict[str, dict]] = {}


@dataclass
class WeatherWindow:
    summary: str
    window_start: Optional[str]
    window_end: Optional[str]
    precipitation_total_mm: Optional[float]
    et0_total_mm: Optional[float]
    tmin_c: Optional[float]
    tmax_c: Optional[float]
    soil_moisture_vwc: Optional[float]
    data_status: str  # current_forecast | historical_reference | unavailable
    source: str

    @property
    def is_unavailable(self) -> bool:
        return self.data_status == "unavailable"


def _load_meteoblue_data() -> None:
    if _WEATHER_CACHE:
        return
    data_file = Path(__file__).resolve().parents[2] / "data_generated" / "Meteoblue dataset"
    try:
        with data_file.open(encoding="utf-8") as file:
            records = json.load(file)
        locations = records[0].get("geometry", {}).get("locationNames", [])
        for location in locations:
            _WEATHER_CACHE[location] = {}
        for entry in records:
            daily = entry.get("timeResolution") == "daily"
            times = entry.get("timeIntervals", [[]])[0]
            for code_block in entry.get("codes", []):
                data = code_block.get("dataPerTimeInterval", [{}])[0].get("data", [])
                for location_index, location in enumerate(locations):
                    if location_index >= len(data):
                        continue
                    for index, timestamp in enumerate(times):
                        if index >= len(data[location_index]):
                            continue
                        key = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
                        values = _WEATHER_CACHE[location].setdefault(
                            key, {"precip": 0.0, "et0": 0.0, "sm": [], "tmin": None, "tmax": None}
                        )
                        value = data[location_index][index]
                        if value is None:
                            continue
                        if daily and code_block.get("aggregation") == "min":
                            values["tmin"] = value
                        elif daily and code_block.get("aggregation") == "max":
                            values["tmax"] = value
                        elif not daily and code_block.get("code") == 61:
                            values["precip"] += value
                        elif not daily and code_block.get("code") == 261:
                            values["et0"] += value
                        elif not daily and code_block.get("code") == 144:
                            values["sm"].append(value)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        logger.warning("Could not load bundled Meteoblue reference data: %s", exc)


def _unavailable(source: str = "Open-Meteo current forecast") -> WeatherWindow:
    return WeatherWindow(FALLBACK_SUMMARY, None, None, None, None, None, None, None, "unavailable", source)


def _historical_window(district: str, reference_date: date) -> WeatherWindow:
    _load_meteoblue_data()
    days = [(reference_date + timedelta(days=offset)).isoformat() for offset in range(FORECAST_DAYS)]
    records = _WEATHER_CACHE.get(district, {})
    if not all(day in records for day in days):
        return _unavailable("Meteoblue ERA5T historical reference")
    window = [records[day] for day in days]
    soil = [value for row in window for value in row["sm"]]
    rain = sum(row["precip"] for row in window)
    return WeatherWindow(
        summary=f"historical reference: {rain:.0f}mm recorded over {FORECAST_DAYS} days",
        window_start=days[0], window_end=days[-1], precipitation_total_mm=rain,
        et0_total_mm=sum(row["et0"] for row in window),
        tmin_c=min(row["tmin"] for row in window if row["tmin"] is not None),
        tmax_c=max(row["tmax"] for row in window if row["tmax"] is not None),
        soil_moisture_vwc=(sum(soil) / len(soil)) if soil else None,
        data_status="historical_reference", source="Meteoblue ERA5T bundled historical reference",
    )


def _fetch(url: str, timeout: float = 6.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def _current_window(district: str) -> WeatherWindow:
    coordinates = DISTRICT_COORDINATES.get(district)
    if coordinates is None:
        return _unavailable("Open-Meteo current forecast (district has no coordinates)")
    latitude, longitude = coordinates
    url = (
        f"{OPEN_METEO_URL}?latitude={latitude}&longitude={longitude}&timezone=auto"
        f"&forecast_days={FORECAST_DAYS}"
        "&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,et0_fao_evapotranspiration"
        "&hourly=soil_moisture_0_to_1cm"
    )
    try:
        data = _fetch(url)
        daily = data["daily"]
        if len(daily["time"]) < FORECAST_DAYS:
            raise ValueError("incomplete five-day forecast")
        hourly_soil = [value for value in data.get("hourly", {}).get("soil_moisture_0_to_1cm", []) if value is not None]
        rain = sum(daily["precipitation_sum"][:FORECAST_DAYS])
        return WeatherWindow(
            summary=f"{rain:.0f}mm forecast over the next {FORECAST_DAYS} days",
            window_start=daily["time"][0], window_end=daily["time"][FORECAST_DAYS - 1],
            precipitation_total_mm=rain,
            et0_total_mm=sum(daily["et0_fao_evapotranspiration"][:FORECAST_DAYS]),
            tmin_c=min(daily["temperature_2m_min"][:FORECAST_DAYS]),
            tmax_c=max(daily["temperature_2m_max"][:FORECAST_DAYS]),
            soil_moisture_vwc=(sum(hourly_soil) / len(hourly_soil)) if hourly_soil else None,
            data_status="current_forecast", source="Open-Meteo five-day forecast",
        )
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Current weather forecast unavailable for %r: %s", district, exc)
        return _unavailable()


def get_weather_window(district: str, reference_date: Optional[date] = None) -> WeatherWindow:
    """Return a five-day current forecast, or an explicitly historical reference window."""
    return _historical_window(district, reference_date) if reference_date else _current_window(district)
