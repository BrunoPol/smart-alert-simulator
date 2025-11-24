"""
Daily runner for Smart Alert Simulator.

- Loads user profiles from config/user_profiles.json
- For each profile:
  - Fetches current weather, forecast, and air quality/pollen
  - Evaluates rules
  - Sends an email with alerts (if any)
"""

from typing import Any, Dict, List
import json
import os

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


def load_profiles() -> List[Dict[str, Any]]:
    """Load all user profiles from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        print(f"No profile file found at {CONFIG_PATH}.")
        return []

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error parsing {CONFIG_PATH}: {exc}")
        return []

    if not isinstance(data, list):
        print(f"Expected a list of profiles in {CONFIG_PATH}.")
        return []

    return data


def run_for_profile(profile: Dict[str, Any], hours: int = 12) -> None:
    """
    Run the full alert flow for a single profile.
    """
    email = profile.get("email")
    city = profile.get("city")

    if not email or not city:
        print("Profile is missing 'email' or 'city', skipping:", profile)
        return

    context = {
        "has_pets": profile.get("has_pets", False),
        "has_plants": profile.get("has_plants", False),
        "sensitive_to_cold": profile.get("sensitive_to_cold", False),
        "sensitive_to_heat": profile.get("sensitive_to_heat", False),
        "sensitive_to_pollution": profile.get("sensitive_to_pollution", False),
        "sensitive_to_allergies": profile.get("sensitive_to_allergies", False),
    }

    print("\n=== Running alerts for profile ===")
    print(f"Email: {email}")
    print(f"City:  {city}")
    print(f"Context: {context}")

    # ---- Current weather ----
    weather = get_current_weather_by_city(city)
    if weather is None:
        print(f"Could not fetch current weather for {city}. Skipping profile.")
        return

    print(f"\nCurrent weather in {city} at {weather['time']}:")
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

    # ---- Rules on current conditions ----
    current_alerts = evaluate_rules(weather, context=context)

        # ---- Rules on current conditions ----
    current_alerts = evaluate_rules(weather, context=context)

    # ---- Forecast ----
    forecast_alerts: List[Any] = []
    forecast_email_lines: list[str] = []  # for email body

    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        print("\nCould not fetch hourly forecast.")
    else:
        # Evaluate forecast-based rules (same as before)
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

        # Build a short forecast summary for the email (first up to 4 hours)
        times = forecast.get("time", [])
        temps = forecast.get("temperature", [])
        app_temps = forecast.get("apparent_temperature") or [None] * len(times)
        uvs = forecast.get("uv_index") or [None] * len(times)
        probs = forecast.get("precipitation_probability") or [None] * len(times)
        winds = forecast.get("wind_speed") or [None] * len(times)

        for t, temp, app, uv, prob, wind in zip(
            times, temps, app_temps, uvs, probs, winds
        ):
            if len(forecast_email_lines) >= 4:
                break  # only include first 4 hours to keep the email short

            feels_str = f"{app:.1f}°C" if app is not None else "n/a"
            uv_str = f"{uv:.1f}" if uv is not None else "n/a"
            prob_str = f"{prob:.0f}%" if prob is not None else "n/a"
            wind_str = f"{wind:.1f} km/h" if wind is not None else "n/a"

            line = (
                f"{t}: {temp:.1f}°C (feels {feels_str}), "
                f"UV {uv_str}, rain {prob_str}, wind {wind_str}"
            )
            forecast_email_lines.append(line)


    # ---- Air quality & pollen ----
    air_quality_alerts: List[Any] = []
    air_quality_summary: Dict[str, str] | None = None

    air_quality = get_air_quality_by_city(city, hours=hours)
    if air_quality is None:
        print("\nCould not fetch air quality / pollen data.")
    else:
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

        print("\nAir quality & pollen (summary):")
        if max_pm25 is not None:
            print(f"  Max PM2.5:   {max_pm25} at {max_pm25_time}")
        if max_pm10 is not None:
            print(f"  Max PM10:    {max_pm10} at {max_pm10_time}")

        pollen_candidates = [
            ("grass", max_grass, max_grass_time),
            ("birch", max_birch, max_birch_time),
            ("ragweed", max_ragweed, max_ragweed_time),
        ]
        pollen_candidates = [(n, v, t) for (n, v, t) in pollen_candidates if v is not None]
        if pollen_candidates:
            pollen_name, pollen_val, pollen_time = max(pollen_candidates, key=lambda x: x[1])
            print(f"  Max pollen:  {pollen_name} = {pollen_val} at {pollen_time}")
            pollen_summary_str = f"{pollen_name} = {pollen_val} at {pollen_time}"
        else:
            print("  Pollen data: n/a")
            pollen_summary_str = "n/a"

        air_quality_summary = {
            "Max PM2.5": f"{max_pm25} at {max_pm25_time}" if max_pm25 is not None else "n/a",
            "Max PM10": f"{max_pm10} at {max_pm10_time}" if max_pm10 is not None else "n/a",
            "Max pollen": pollen_summary_str,
        }

        air_quality_alerts = evaluate_air_quality_rules(air_quality, context=context)

    # ---- Print alert overview ----
    print("\nAlerts (current conditions):")
    if not current_alerts:
        print("  None.")
    else:
        for alert in current_alerts:
            print(f"- [{alert.severity.upper()}] {alert.message}")
            print(f"    Reason: {alert.reason}")

    print("\nAlerts (forecast & air quality / pollen):")
    combined_future_alerts = list(forecast_alerts) + list(air_quality_alerts)
    if not combined_future_alerts:
        print("  None.")
    else:
        for alert in combined_future_alerts:
            print(f"- [{alert.severity.upper()}] {alert.message}")
            print(f"    Reason: {alert.reason}")

    # ---- Email notification ----
    print("\nSending email notification (if alerts exist and email is enabled)...")
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
        air_quality_alerts=air_quality_alerts,
        air_quality_summary=air_quality_summary,
        forecast_lines=forecast_email_lines,
        email_to=email,
    )

    print("=== Done for this profile ===\n")


def main() -> None:
    print("Loading user profiles...")
    profiles = load_profiles()
    if not profiles:
        print("No profiles found. Nothing to do.")
        return

    for profile in profiles:
        run_for_profile(profile, hours=12)

    print("All profiles processed.")


if __name__ == "__main__":
    main()

