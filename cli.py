from typing import Dict, Any, Optional, List
import json
import os

import requests
from dotenv import load_dotenv

from src.weather_client import (
    get_current_weather_by_city,
    get_hourly_forecast_by_city,
    get_air_quality_by_city,
)
from src.rules_engine import (
    evaluate_rules,
    evaluate_forecast_rules,
    evaluate_air_quality_rules,
)
from src.alerts import send_alerts_email_if_configured

load_dotenv()

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "user_profiles.json")

PROFILE_API_URL = os.getenv("PROFILE_API_URL")
PROFILE_API_SECRET = os.getenv("PROFILE_API_SECRET")


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

    has_pets = ask_yes_no(
        "Do you have pets that spend time outdoors?"
    )
    has_plants = ask_yes_no(
        "Do you have outdoor plants, balcony plants, or a garden?"
    )
    sensitive_to_cold = ask_yes_no(
        "Would you like extra tips when it’s cold outside?"
    )
    sensitive_to_heat = ask_yes_no(
        "Would you like extra tips when it’s hot outside?"
    )
    sensitive_to_pollution = ask_yes_no(
        "Does anyone in your household have asthma or other breathing problems?"
    )
    sensitive_to_allergies = ask_yes_no(
        "Does anyone in your household have pollen allergies (hay fever)?"
    )

    context = {
        "has_pets": has_pets,
        "has_plants": has_plants,
        "sensitive_to_cold": sensitive_to_cold,
        "sensitive_to_heat": sensitive_to_heat,
        "sensitive_to_pollution": sensitive_to_pollution,
        "sensitive_to_allergies": sensitive_to_allergies,
    }

    print("\nContext set to:")
    for key, value in context.items():
        print(f"  {key}: {value}")

    return context



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
            print(f"Server sync failed: {resp.status_code} {resp.text}")
    except Exception as exc:
        print(f"Could not sync profile to server: {exc}")


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
    - fetch air quality & pollen
    - evaluate current, forecast-based and air-quality rules
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
    if weather.get("apparent_temperature") is not None:
        print(f"  Feels like:  {weather['apparent_temperature']} °C")
    print(f"  Humidity:    {weather['humidity']} %")
    print(f"  Precip:      {weather['precipitation']} mm")
    print(f"  Code:        {weather['weather_code']}")
    if weather.get("uv_index") is not None:
        print(f"  UV index:    {weather['uv_index']}")
    if weather.get("wind_speed") is not None:
        print(f"  Wind:        {weather['wind_speed']} km/h")
    print()

    # ---- Evaluate current-conditions rules ----
    current_alerts = evaluate_rules(weather, context=context)

    # ---- Fetch hourly forecast ----
    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        print("Could not fetch hourly forecast.")
        forecast_alerts: List[Any] = []
    else:
        print(f"Next {hours} hours forecast (temperature, feels-like, UV, rain chance, wind):")
        for t, temp, app_temp, uv, prob, wind in zip(
            forecast["time"],
            forecast["temperature"],
            forecast.get("apparent_temperature", []),
            forecast.get("uv_index", []),
            forecast.get("precipitation_probability", []),
            forecast.get("wind_speed", []),
        ):
            app_str = f"{app_temp} °C" if app_temp is not None else "n/a"
            uv_str = f"{uv}" if uv is not None else "n/a"
            prob_str = f"{prob}%" if prob is not None else "n/a"
            wind_str = f"{wind} km/h" if wind is not None else "n/a"
            print(f"  {t}: {temp} °C (feels {app_str}), UV {uv_str}, rain {prob_str}, wind {wind_str}")
        print()

        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

        # ---- Fetch air quality & pollen ----
    air_quality_alerts: List[Any] = []
    air_quality_summary_dict: dict | None = None  # NEW: initialize summary

    air_quality = get_air_quality_by_city(city, hours=hours)
    if air_quality is None:
        print("Could not fetch air quality / pollen data.")
    else:
        # Show simple summary: max PM2.5, PM10, and highest pollen
        times = air_quality.get("time", [])
        pm25 = air_quality.get("pm2_5", [])
        pm10 = air_quality.get("pm10", [])
        grass = air_quality.get("grass_pollen", [])
        birch = air_quality.get("birch_pollen", [])
        ragweed = air_quality.get("ragweed_pollen", [])

        def max_with_time(series):
            best_val, best_time = None, None
            for t, v in zip(times, series):
                if v is not None and (best_val is None or v > best_val):
                    best_val, best_time = v, t
            return best_val, best_time

        max_pm25, max_pm25_time = max_with_time(pm25)
        max_pm10, max_pm10_time = max_with_time(pm10)
        max_grass, max_grass_time = max_with_time(grass)
        max_birch, max_birch_time = max_with_time(birch)
        max_ragweed, max_ragweed_time = max_with_time(ragweed)

        print("Air quality & pollen (next hours):")
        if max_pm25 is not None:
            print(f"  Max PM2.5:   {max_pm25} at {max_pm25_time}")
        if max_pm10 is not None:
            print(f"  Max PM10:    {max_pm10} at {max_pm10_time}")

        # Show the highest pollen among the 3
        pollen_candidates = [
            ("grass", max_grass, max_grass_time),
            ("birch", max_birch, max_birch_time),
            ("ragweed", max_ragweed, max_ragweed_time),
        ]
        pollen_candidates = [(n, v, t) for (n, v, t) in pollen_candidates if v is not None]
        if pollen_candidates:
            name, val, t = max(pollen_candidates, key=lambda x: x[1])
            print(f"  Max pollen:  {name} = {val} at {t}")
        else:
            print("  Pollen data: n/a")

        print()

        # NEW: build a small summary dict for the email
        air_quality_summary_dict = {
            "Max PM2.5": f"{max_pm25} at {max_pm25_time}" if max_pm25 is not None else "n/a",
            "Max PM10": f"{max_pm10} at {max_pm10_time}" if max_pm10 is not None else "n/a",
            "Max pollen": (
                f"{name} = {val} at {t}" if pollen_candidates else "n/a"
            ),
        }

        air_quality_alerts = evaluate_air_quality_rules(air_quality, context=context)

    # ---- Combine alerts ----
    all_forecast_like_alerts = list(forecast_alerts) + list(air_quality_alerts)

    # ---- Print combined alerts ----
    if not current_alerts and not all_forecast_like_alerts:
        print("No alerts triggered (current, forecast, or air quality).")
    else:
        print("Alerts (current conditions):")
        if not current_alerts:
            print("  None.")
        else:
            for alert in current_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

        print("\nAlerts (forecast & air quality / pollen):")
        if not all_forecast_like_alerts:
            print("  None.")
        else:
            for alert in all_forecast_like_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

    # ---- Email notification ----
    print("\nEmail notification:")
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
        air_quality_alerts=air_quality_alerts,
        air_quality_summary=air_quality_summary_dict,
        email_to=notification_email,
    )


    print("\n==== End of run ====\n")


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
        "sensitive_to_pollution": context["sensitive_to_pollution"],
        "sensitive_to_allergies": context["sensitive_to_allergies"],
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

    # Sync to PythonAnywhere
    sync_profile_to_server(profile)

    # Optional: ask if they want to run a test immediately
    if ask_yes_no("Do you want to run the simulator now with this profile?"):
        run_alert_flow(city, context, notification_email=email, hours=6)


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


