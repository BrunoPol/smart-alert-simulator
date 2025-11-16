"""
Simple command-line interface (CLI) for the Smart Alert Simulator.

Run it from the project root with:

    python cli.py
"""

import os
from typing import Dict, Any, Optional

from src.weather_client import (
    get_current_weather_by_city,
    get_hourly_forecast_by_city,
)
from src.rules_engine import evaluate_rules, evaluate_forecast_rules
from src.alerts import send_alerts_email_if_configured


def clear_screen() -> None:
    """Clear the terminal screen (works on Windows, macOS, Linux)."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header(title: str) -> None:
    """Print a nice section header."""
    print("=" * 50)
    print(title)
    print("=" * 50)


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
    print_header("Choose a city")
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
    print_header("Household context")

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

    input("\nPress Enter to continue...")
    return context


def run_alert_flow(city: str, context: Dict[str, Any], hours: int = 6) -> None:
    """
    Run the full alert flow:
    - fetch current weather
    - fetch hourly forecast
    - evaluate current and forecast-based rules
    - print alerts
    - trigger email notification (simulated or real)
    """
    clear_screen()
    print_header("Smart Alert Simulator – Run")
    print(f"City: {city}")
    print(f"Context: {context}")
    print()

    # ---- Fetch current weather ----
    weather: Optional[dict] = get_current_weather_by_city(city)
    if weather is None:
        print(f"Could not find weather data for city: {city}")
        return

    print("Current weather:")
    print(f"  Time:        {weather['time']}")
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
    print_header("Alerts")
    if not current_alerts and not forecast_alerts:
        print("No alerts triggered (current or forecast).")
    else:
        print("Current conditions:")
        if not current_alerts:
            print("  None.")
        else:
            for alert in current_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

        print("\nForecast-based:")
        if not forecast_alerts:
            print("  None.")
        else:
            for alert in forecast_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

    # ---- Email notification ----
    print_header("Email notification")
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
    )

    print("\n==== End of run ====\n")
    input("Press Enter to return to the main menu...")


def main() -> None:
    """Top-level CLI menu loop."""
    while True:
        clear_screen()
        print_header("Smart Alert Simulator – CLI")
        print("1) Run simulator")
        print("2) Exit")

        choice = input("Your choice [1-2]: ").strip()
        if choice == "1":
            city = choose_city()
            context = build_context_from_user()
            run_alert_flow(city, context, hours=6)
        elif choice == "2":
            clear_screen()
            print("Goodbye!")
            break
        else:
            print("Please choose 1 or 2.")
            input("Press Enter to continue...")


if __name__ == "__main__":
    main()

