"""
Send alerts for all registered user profiles.

Intended to be run once per day, e.g.:

    python send_all_alerts.py

On a server (or PythonAnywhere task scheduler), this script:
- reads config/user_profiles.json
- for each profile: fetches weather, evaluates rules
- sends an email if there are alerts
"""

import json
import os
from typing import Any, Dict, List

from src.weather_client import (
    get_current_weather_by_city,
    get_hourly_forecast_by_city,
)
from src.rules_engine import evaluate_rules, evaluate_forecast_rules
from src.alerts import send_alerts_email_if_configured


CONFIG_PATH = os.path.join("config", "user_profiles.json")


def load_user_profiles() -> List[Dict[str, Any]]:
    """Load all user profiles from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        print(f"No user profile config found at {CONFIG_PATH}.")
        return []

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"Error parsing {CONFIG_PATH}: {exc}")
            return []

    if not isinstance(data, list):
        print(f"Expected a list of profiles in {CONFIG_PATH}.")
        return []

    return data


def run_for_profile(profile: Dict[str, Any], hours: int = 12) -> None:
    """Run the alert flow for a single user profile."""
    email = profile.get("email")
    city = profile.get("city")

    if not email or not city:
        print("Profile is missing 'email' or 'city', skipping:", profile)
        return

    context: Dict[str, Any] = {
        "has_pets": profile.get("has_pets", False),
        "has_plants": profile.get("has_plants", False),
        "sensitive_to_cold": profile.get("sensitive_to_cold", False),
        "sensitive_to_heat": profile.get("sensitive_to_heat", False),
    }

    print("\n=== Running alerts for profile ===")
    print(f"Email: {email}")
    print(f"City:  {city}")
    print(f"Context: {context}")
    print()

    # ---- Fetch current weather ----
    weather = get_current_weather_by_city(city)
    if weather is None:
        print(f"Could not fetch weather data for city: {city}")
        return

    print(f"Current weather in {city} at {weather['time']}:")
    print(f"  Temperature: {weather['temperature']} °C")
    print(f"  Humidity:    {weather['humidity']} %")
    print(f"  Precip:      {weather['precipitation']} mm")
    print(f"  Code:        {weather['weather_code']}")
    print()

    # ---- Evaluate alerts ----
    current_alerts = evaluate_rules(weather, context=context)

    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        print("Could not fetch hourly forecast.")
        forecast_alerts = []
    else:
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

    # ---- Send email ----
    print("Sending email notification (if alerts exist and email is enabled)...")
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
        email_to=email,  # override EMAIL_TO from .env
    )

    print("=== Done for this profile ===\n")


def main() -> None:
    print("Loading user profiles...")
    profiles = load_user_profiles()
    if not profiles:
        print("No profiles found. Nothing to do.")
        return

    for profile in profiles:
        run_for_profile(profile, hours=12)

    print("All profiles processed.")


if __name__ == "__main__":
    main()
