

from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timedelta  

import requests

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def get_current_weather(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Fetch current weather for a given location from Open-Meteo.

    :param latitude: Latitude in degrees, e.g. 47.3769 for Zurich.
    :param longitude: Longitude in degrees, e.g. 8.5417 for Zurich.
    :return: Dictionary with selected weather fields.
    :raises ValueError: If the API response is missing expected data.
    """

    params = {
        "latitude": latitude,
        "longitude": longitude,
        # Request only the desired current weather fields.
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,uv_index",
    }

    response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    current = payload.get("current")
    if not current:
        raise ValueError("Open-Meteo response missing 'current' data.")

    # Build a normalized view so callers work with a stable shape.
    return {
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "weather_code": current.get("weather_code"),
        "time": current.get("time"),
        "uv_index": current.get("uv_index"),
    }

def get_hourly_forecast(
    latitude: float,
    longitude: float,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Fetch hourly forecast for the next `hours` hours for a given location from Open-Meteo.

    :param latitude: Latitude in degrees.
    :param longitude: Longitude in degrees.
    :param hours: Number of future hours to include.
    :return: Dictionary with 'time' list and per-hour series (temperature, humidity, precipitation, uv_index).
    """
    # We use hourly parameters; Open-Meteo returns arrays indexed by time.
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,weather_code,uv_index",
        "forecast_days": 3,  # gives up to 72h, we'll slice to 'hours' below
    }

    response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly")
    if not hourly:
        raise ValueError("Open-Meteo response missing 'hourly' data.")

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    hums = hourly.get("relative_humidity_2m", [])
    precs = hourly.get("precipitation", [])
    codes = hourly.get("weather_code", [])
    uv = hourly.get("uv_index", [])

    # Slice to the requested number of hours (if available)
    n = min(hours, len(times))
    return {
        "time": times[:n],
        "temperature": temps[:n],
        "humidity": hums[:n],
        "precipitation": precs[:n],
        "weather_code": codes[:n],
        "uv_index": uv[:n] if uv else [None] * n,
    }



def get_coordinates_for_city(city_name: str) -> Optional[Tuple[float, float]]:
    """
    Look up latitude and longitude for a city name using Open-Meteo's geocoding API.
    Return (latitude, longitude) if a result is found, otherwise None.
    """

    params = {
        "name": city_name,
        "count": 3,
    }
    response = requests.get(GEOCODING_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    # Results are sorted by relevance, so pick the first entry.
    results = payload.get("results") or []
    if not results:
        return None

    first = results[0]
    latitude = first.get("latitude")
    longitude = first.get("longitude")
    if latitude is None or longitude is None:
        return None

    return latitude, longitude

def get_current_weather_by_city(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper that:
    - looks up coordinates for the given city
    - if found, calls get_current_weather(latitude, longitude)
    - returns the weather dict, or None if the city is not found.
    """
    coords = get_coordinates_for_city(city_name)
    if coords is None:
        return None

    latitude, longitude = coords
    # Make sure they are floats (in case the API returns Decimal/other types)
    return get_current_weather(float(latitude), float(longitude))

def get_hourly_forecast_by_city(
    city_name: str,
    hours: int = 24,
) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper that:
    - looks up coordinates for the given city
    - if found, calls get_hourly_forecast(latitude, longitude, hours)
    - returns the forecast dict, or None if the city is not found.
    """
    coords = get_coordinates_for_city(city_name)
    if coords is None:
        return None

    latitude, longitude = coords
    return get_hourly_forecast(float(latitude), float(longitude), hours=hours)

def get_recent_hourly_history(
    latitude: float,
    longitude: float,
    past_days: int = 1,
) -> Dict[str, Any]:
    """
    Fetch recent hourly history for the past `past_days` (up to 7) for a location.

    This can be used for rules that depend on how the weather behaved recently,
    for example: "it has been hot for the last 3 days".
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,weather_code,uv_index",
        "past_days": past_days,
        "forecast_days": 0,  # we only care about the past here
    }

    response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly")
    if not hourly:
        raise ValueError("Open-Meteo response missing 'hourly' data for history.")

    return {
        "time": hourly.get("time", []),
        "temperature": hourly.get("temperature_2m", []),
        "humidity": hourly.get("relative_humidity_2m", []),
        "precipitation": hourly.get("precipitation", []),
        "weather_code": hourly.get("weather_code", []),
        "uv_index": hourly.get("uv_index", []),
    }

def get_recent_hourly_history_by_city(
    city_name: str,
    past_days: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper to fetch recent hourly history by city name.
    """
    coords = get_coordinates_for_city(city_name)
    if coords is None:
        return None

    latitude, longitude = coords
    return get_recent_hourly_history(float(latitude), float(longitude), past_days=past_days)
