"""
Simple command-line interface (CLI) for the Smart Alert Simulator.

Run it from the project root with:

    python cli.py

Features:
- Run the simulator once interactively (choose city, context, email).
- Register/update a daily email profile (saved to config/user_profiles.json),
  which is used by send_all_alerts.py for scheduled notifications.
"""

import json
import os
from typing import Dict, Any, Optional, List
import requests
from dotenv import load_dotenv  # NEW
load_dotenv()  # to get PROFILE_API_* from .env

PROFILE_API_URL = os.getenv("PROFILE_API_URL")
PROFILE_API_SECRET = os.getenv("PROFILE_API_SECRET")

from src.weather_client import (
    get_current_weather_by_city,
    get_hourly_forecast_by_city,
)
from src.rules_engine import evaluate_rules, evaluate_forecast_rules
from src.alerts import send_alerts_email_if_configured

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "user_profiles.json")


def ask_yes_no(prompt: str) -> bool:
    """Ask the user a yes/no question and return True for yes, False for no."""
    while True:
        answer = input(prompt + " [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer with 'y' or 'n'.")


def choose_city() -> str:
    """Let the user choose a city from a small menu or enter a custom one."""
    print("Choose a city:")
    print("  1) Lisbon")
    print("  2) Oslo")
    print("  3) Dubai")
    print("  4) Reykjavik")
    print("  5) Enter custom city name")

    while True:
        choice = input("Your choice [1-5]: ").strip()
        if choice == "1":
            return "Lisbon"
        if choice == "2":
            return "Oslo"
        if choice == "3":
            return "Dubai"
        if choice == "4":
            return "Reykjavik"
        if choice == "5":
            city = input("Enter city name: ").strip()
            if city:
                return city
            print("City name cannot be empty.")
        else:
            print("Please choose a number between 1 and 5.")


def build_context_from_user() -> Dict[str, Any]:
    """Ask the user a few questions to build the context dict."""
    print("\nNow tell me a bit about your household:")

    has_pets = ask_yes_no("Do you have pets?")
    has_plants = ask_yes_no("Do you have plants (especially outdoors)?")
    sensitive_to_cold = ask_yes_no("Is someone in the household sensitive to cold?")
    sensitive_to_heat = ask_yes_no("Is someone in the household sensitive to heat?")

    context = {
        "has_pets": has_pets,
        "has_plants": has_plants,
        "sensitive_to_cold": sensitive_to_cold,
        "sensitive_to_heat": sensitive_to_heat,
    }

    print("\nContext set to:")
    for key, value in context.items():
        print(f"  {key}: {value}")

    return context


def run_alert_flow(
    city: str,
    context: Dict[str, Any],
    notification_email: Optional[str],
    hours: int = 6,
) -> None:
    """
    Run the full alert flow:
    - fetch current weather
    - fetch hourly forecast
    - evaluate current and forecast-based rules
    - print alerts
    - trigger email notification (simulated or real)
    """
    print("\n==== Running Smart Alert Simulator ====\n")
    print(f"City: {city}")
    print(f"Context: {context}")
    print(f"Notification email override: {notification_email}")
    print()

    # ---- Fetch current weather ----
    weather: Optional[dict] = get_current_weather_by_city(city)
    if weather is None:
        print(f"Could not find weather data for city: {city}")
        return

    print(f"Current weather in {city} at {weather['time']}:")
    print(f"  Temperature: {weather['temperature']} °C")
    print(f"  Humidity:    {weather['humidity']} %")
    print(f"  Precip:      {weather['precipitation']} mm")
    print(f"  Code:        {weather['weather_code']}")
    print()

    # ---- Evaluate current-conditions rules ----
    current_alerts = evaluate_rules(weather, context=context)

    # ---- Fetch hourly forecast ----
    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        print("Could not fetch hourly forecast.")
        forecast_alerts = []
    else:
        print(f"Next {hours} hours forecast (temperature & UV index):")
        for t, temp, uv in zip(
            forecast["time"],
            forecast["temperature"],
            forecast["uv_index"],
        ):
            print(f"  {t}: {temp} °C, UV index: {uv}")
        print()

        # ---- Forecast-based alerts ----
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

    # ---- Print combined alerts ----
    if not current_alerts and not forecast_alerts:
        print("No alerts triggered (current or forecast).")
    else:
        print("Alerts (current conditions):")
        if not current_alerts:
            print("  None.")
        else:
            for alert in current_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

        print("\nAlerts (forecast-based):")
        if not forecast_alerts:
            print("  None.")
        else:
            for alert in forecast_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

    # ---- Email notification ----
    print("\nEmail notification:")
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
        email_to=notification_email,
    )

    print("\n==== End of run ====\n")


# ---------- Profile storage helpers ----------


def load_profiles() -> List[Dict[str, Any]]:
    """Load all user profiles from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return []

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Warning: could not parse {CONFIG_PATH}: {exc}")
        return []

    if not isinstance(data, list):
        print(f"Warning: expected a list of profiles in {CONFIG_PATH}.")
        return []

    return data


def save_profiles(profiles: List[Dict[str, Any]]) -> None:
    """Save all user profiles to the JSON file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    print(f"Profiles saved to {CONFIG_PATH}.")


def register_profile() -> None:
    """
    Interactively create or update a user profile for daily emails.
    The profile is stored in config/user_profiles.json.
    """
    print("\n=== Register / Update Daily Email Profile ===")

    city = choose_city()
    context = build_context_from_user()
    print()

    while True:
        email = input("Enter the email address to receive daily alerts: ").strip()
        if email:
            break
        print("Email cannot be empty.")

    profile = {
        "email": email,
        "city": city,
        "has_pets": context["has_pets"],
        "has_plants": context["has_plants"],
        "sensitive_to_cold": context["sensitive_to_cold"],
        "sensitive_to_heat": context["sensitive_to_heat"],
    }

    profiles = load_profiles()

    # Update if email already exists, otherwise append.
    for i, existing in enumerate(profiles):
        if existing.get("email") == email:
            profiles[i] = profile
            print(f"\nUpdated existing profile for {email}.")
            break
    else:
        profiles.append(profile)
        print(f"\nAdded new profile for {email}.")

    save_profiles(profiles)

    sync_profile_to_server(profile)

    # Optional: ask if they want to run a test immediately
    if ask_yes_no("Do you want to run the simulator now with this profile?"):
        run_alert_flow(city, context, notification_email=email, hours=6)

def sync_profile_to_server(profile: Dict[str, Any]) -> None:
    """Send the profile to the server's /register_profile API (best-effort)."""
    if not PROFILE_API_URL or not PROFILE_API_SECRET:
        print("PROFILE_API_URL or PROFILE_API_SECRET not set; skipping server sync.")
        return

    payload = dict(profile)
    payload["api_key"] = PROFILE_API_SECRET

    try:
        resp = requests.post(PROFILE_API_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            print("Profile synced to server successfully.")
        else:
            print(
                f"Server sync failed: {resp.status_code} {resp.text}"
            )
    except Exception as exc:
        print(f"Could not sync profile to server: {exc}")



def main() -> None:
    """Top-level CLI menu loop."""
    print("Welcome to the Smart Alert Simulator CLI!")
    print("----------------------------------------")

    while True:
        print("\nMain menu:")
        print("  1) Run simulator once (interactive)")
        print("  2) Register / update daily email profile")
        print("  3) Exit")

        choice = input("Your choice [1-3]: ").strip()
        if choice == "1":
            city = choose_city()
            context = build_context_from_user()
            notification_email = input(
                "\nEnter email address for this run "
                "(leave empty to use default from .env): "
            ).strip() or None
            run_alert_flow(city, context, notification_email=notification_email, hours=6)
        elif choice == "2":
            register_profile()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()


