from typing import Any, Dict, Optional, Tuple

import requests

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


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
        # Request desired current weather fields.
        "current": (
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "precipitation,"
            "weather_code,"
            "uv_index,"
            "wind_speed_10m"
        ),
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
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "weather_code": current.get("weather_code"),
        "time": current.get("time"),
        "uv_index": current.get("uv_index"),
        "wind_speed": current.get("wind_speed_10m"),
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
    :return: Dictionary with 'time' list and per-hour series
             (temperature, humidity, precipitation, uv_index, apparent_temperature,
              precipitation_probability, wind_speed, visibility, weather_code).
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "precipitation,"
            "precipitation_probability,"
            "weather_code,"
            "uv_index,"
            "wind_speed_10m,"
            "visibility"
        ),
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
    app_temps = hourly.get("apparent_temperature", [])
    hums = hourly.get("relative_humidity_2m", [])
    precs = hourly.get("precipitation", [])
    precip_probs = hourly.get("precipitation_probability", [])
    codes = hourly.get("weather_code", [])
    uv = hourly.get("uv_index", [])
    wind = hourly.get("wind_speed_10m", [])
    visibility = hourly.get("visibility", [])

    n = min(hours, len(times))
    return {
        "time": times[:n],
        "temperature": temps[:n],
        "apparent_temperature": app_temps[:n] if app_temps else [None] * n,
        "humidity": hums[:n],
        "precipitation": precs[:n],
        "precipitation_probability": precip_probs[:n] if precip_probs else [None] * n,
        "weather_code": codes[:n],
        "uv_index": uv[:n] if uv else [None] * n,
        "wind_speed": wind[:n] if wind else [None] * n,
        "visibility": visibility[:n] if visibility else [None] * n,
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
    This can be used for rules that depend on how the weather behaved recently.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "temperature_2m,"
            "apparent_temperature,"
            "relative_humidity_2m,"
            "precipitation,"
            "weather_code,"
            "uv_index,"
            "wind_speed_10m,"
            "visibility"
        ),
        "past_days": past_days,
        "forecast_days": 0,
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
        "apparent_temperature": hourly.get("apparent_temperature", []),
        "humidity": hourly.get("relative_humidity_2m", []),
        "precipitation": hourly.get("precipitation", []),
        "weather_code": hourly.get("weather_code", []),
        "uv_index": hourly.get("uv_index", []),
        "wind_speed": hourly.get("wind_speed_10m", []),
        "visibility": hourly.get("visibility", []),
    }


def get_recent_hourly_history_by_city(
    city_name: str,
    past_days: int = 1,
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper to fetch recent hourly history by city name."""
    coords = get_coordinates_for_city(city_name)
    if coords is None:
        return None

    latitude, longitude = coords
    return get_recent_hourly_history(float(latitude), float(longitude), past_days=past_days)


# ---- Air quality / pollen helpers (not yet wired into main flow, but ready to use) ----


def get_air_quality(
    latitude: float,
    longitude: float,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Fetch hourly air quality & pollen forecast for the next `hours` hours.

    Returns a dict with time, pm2_5, pm10, and some pollen species if available.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "pm2_5,pm10,grass_pollen,birch_pollen,ragweed_pollen,uv_index",
        "forecast_days": 3,
    }

    response = requests.get(AIR_QUALITY_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly")
    if not hourly:
        raise ValueError("Air quality API response missing 'hourly' data.")

    times = hourly.get("time", [])
    pm25 = hourly.get("pm2_5", [])
    pm10 = hourly.get("pm10", [])
    grass = hourly.get("grass_pollen", [])
    birch = hourly.get("birch_pollen", [])
    ragweed = hourly.get("ragweed_pollen", [])
    uv = hourly.get("uv_index", [])

    n = min(hours, len(times))
    return {
        "time": times[:n],
        "pm2_5": pm25[:n] if pm25 else [None] * n,
        "pm10": pm10[:n] if pm10 else [None] * n,
        "grass_pollen": grass[:n] if grass else [None] * n,
        "birch_pollen": birch[:n] if birch else [None] * n,
        "ragweed_pollen": ragweed[:n] if ragweed else [None] * n,
        "uv_index": uv[:n] if uv else [None] * n,
    }


def get_air_quality_by_city(
    city_name: str,
    hours: int = 24,
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper for air quality & pollen by city name."""
    coords = get_coordinates_for_city(city_name)
    if coords is None:
        return None

    latitude, longitude = coords
    return get_air_quality(float(latitude), float(longitude), hours=hours)

