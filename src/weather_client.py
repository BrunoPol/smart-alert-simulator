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
    from datetime import datetime, timezone
    
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

    # Find the starting index from current time
    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    start_idx = 0
    for i, time_str in enumerate(times):
        # Parse the forecast time - Open-Meteo times are in ISO format
        if time_str.endswith('Z'):
            forecast_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        else:
            # Handle case where timezone might already be included or it's local time
            try:
                forecast_time = datetime.fromisoformat(time_str)
                if forecast_time.tzinfo is None:
                    forecast_time = forecast_time.replace(tzinfo=timezone.utc)
            except ValueError:
                # If parsing fails, skip timezone comparison and use original logic
                start_idx = 0
                break
                
        if forecast_time >= current_hour:
            start_idx = i
            break
    
    # Slice from current hour for the requested number of hours
    end_idx = min(start_idx + hours, len(times))
    
    def slice_list(lst, default_val=None):
        if not lst:
            return [default_val] * (end_idx - start_idx)
        return lst[start_idx:end_idx]
    
    return {
        "time": times[start_idx:end_idx],
        "temperature": slice_list(temps),
        "apparent_temperature": slice_list(app_temps),
        "humidity": slice_list(hums),
        "precipitation": slice_list(precs),
        "precipitation_probability": slice_list(precip_probs),
        "weather_code": slice_list(codes),
        "uv_index": slice_list(uv),
        "wind_speed": slice_list(wind),
        "visibility": slice_list(visibility),
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
    from datetime import datetime, timezone
    
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

    # Find the starting index from current time (same logic as weather forecast)
    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    start_idx = 0
    for i, time_str in enumerate(times):
        # Parse the forecast time - Open-Meteo times are in ISO format
        if time_str.endswith('Z'):
            forecast_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        else:
            # Handle case where timezone might already be included or it's local time
            try:
                forecast_time = datetime.fromisoformat(time_str)
                if forecast_time.tzinfo is None:
                    forecast_time = forecast_time.replace(tzinfo=timezone.utc)
            except ValueError:
                # If parsing fails, skip timezone comparison and use original logic
                start_idx = 0
                break
                
        if forecast_time >= current_hour:
            start_idx = i
            break
    
    # Slice from current hour for the requested number of hours
    end_idx = min(start_idx + hours, len(times))
    
    def slice_list(lst, default_val=None):
        if not lst:
            return [default_val] * (end_idx - start_idx)
        return lst[start_idx:end_idx]

    return {
        "time": times[start_idx:end_idx],
        "pm2_5": slice_list(pm25),
        "pm10": slice_list(pm10),
        "grass_pollen": slice_list(grass),
        "birch_pollen": slice_list(birch),
        "ragweed_pollen": slice_list(ragweed),
        "uv_index": slice_list(uv),
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

