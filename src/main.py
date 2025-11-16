from typing import Optional

from weather_client import get_current_weather_by_city
from rules_engine import evaluate_rules


def main():
    """
    Entry point for the Smart Alert Simulator.

    Steps:
    - Choose a city
    - Define a simple user context (pets, plants, sensitivities)
    - Fetch current weather using Open-Meteo
    - Evaluate rule-based alerts
    - Print results
    """
    city = "Oslo"  # change this to test other cities

    # ---- User context (pretend this is your household profile) ----
    context = {
        "has_pets": True,
        "has_plants": True,
        "sensitive_to_cold": False,
        "sensitive_to_heat": True,
    }

    # ---- Fetch weather ----
    weather: Optional[dict] = get_current_weather_by_city(city)

    if weather is None:
        print(f"Could not find weather data for city: {city}")
        return

    print(f"Weather in {city} at {weather['time']}:")
    print(f"  Temperature: {weather['temperature']} °C")
    print(f"  Humidity:    {weather['humidity']} %")
    print(f"  Precip:      {weather['precipitation']} mm")
    print(f"  Code:        {weather['weather_code']}")
    print()  # blank line for readability

    # ---- Evaluate rules ----
    alerts = evaluate_rules(weather, context=context)

    if not alerts:
        print("No alerts triggered.")
    else:
        print("Alerts:")
        for alert in alerts:
            print(f"- [{alert.severity.upper()}] {alert.message}")
            print(f"    Reason: {alert.reason}")


if __name__ == "__main__":
    main()

