"""
Gather all environmental inputs: sun position + OpenWeatherMap weather data.
Returns EnvironmentState dataclass ready for the palette engine.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import zoneinfo

import requests
from astral import LocationInfo
from astral.sun import elevation, azimuth

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentState:
    # Sun
    sun_elevation: float          # degrees, -90 to +90
    sun_azimuth: float            # degrees, 0-360
    # Weather
    condition: str                # e.g. "Clear", "Rain", "Snow", "Fog", "Clouds"
    condition_id: int             # OWM weather condition code
    cloud_cover: float            # 0-100 %
    temperature_c: float          # Celsius
    humidity: float               # 0-100 %
    visibility_m: float           # metres (max 10000)
    wind_speed_ms: float          # m/s
    # Derived
    is_rain: bool = False
    is_snow: bool = False
    is_fog: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def get_sun_position(dt: datetime, lat: float = 49.3200, lon: float = -123.0724) -> tuple[float, float]:
    """Return (elevation_degrees, azimuth_degrees) for given datetime and location."""
    loc = LocationInfo(latitude=lat, longitude=lon)
    elev = elevation(loc.observer, dt)
    azim = azimuth(loc.observer, dt)
    return round(float(elev), 2), round(float(azim), 2)


def fetch_weather(api_key: str, lat: float = 49.3200, lon: float = -123.0724) -> dict:
    """Fetch current weather from OpenWeatherMap. Returns raw JSON."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_weather(data: dict) -> dict:
    """Extract the fields we care about from OWM response."""
    weather = data["weather"][0]
    condition_id = weather["id"]
    return {
        "condition": weather["main"],
        "condition_id": condition_id,
        "cloud_cover": float(data.get("clouds", {}).get("all", 0)),
        "temperature_c": float(data["main"]["temp"]),
        "humidity": float(data["main"]["humidity"]),
        "visibility_m": float(data.get("visibility", 10000)),
        "wind_speed_ms": float(data.get("wind", {}).get("speed", 0)),
        "is_rain": 200 <= condition_id < 700,
        "is_snow": 600 <= condition_id < 700,
        "is_fog": 700 <= condition_id < 800,
    }


def get_environment(api_key: str, lat: float = 49.3200, lon: float = -123.0724) -> EnvironmentState:
    """Fetch all environment data and return an EnvironmentState."""
    now = datetime.now(zoneinfo.ZoneInfo("America/Vancouver"))
    elev, azim = get_sun_position(now, lat, lon)

    weather_data = fetch_weather(api_key, lat, lon)
    w = parse_weather(weather_data)

    state = EnvironmentState(
        sun_elevation=elev,
        sun_azimuth=azim,
        **w,
        timestamp=now,
    )
    logger.info(
        "Environment: elev=%.1f° clouds=%d%% condition=%s temp=%.1f°C",
        state.sun_elevation, state.cloud_cover, state.condition, state.temperature_c
    )
    return state
