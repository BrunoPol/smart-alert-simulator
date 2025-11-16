from typing import Optional

from weather_client import (
    get_current_weather_by_city,
    get_hourly_forecast_by_city,
)
from rules_engine import evaluate_rules, evaluate_forecast_rules
from alerts import send_alerts_email_if_configured


def main():
    """
    Entry point for the Smart Alert Simulator.

    Steps:
    - Choose a city
    - Define a simple user context (pets, plants, sensitivities)
    - Fetch current weather using Open-Meteo
    - Evaluate rule-based alerts (current + forecast)
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

    # ---- Fetch current weather ----
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

    # ---- Evaluate current-conditions rules ----
    alerts = evaluate_rules(weather, context=context)

    # ---- Fetch hourly forecast (next 6 hours) ----
    forecast = get_hourly_forecast_by_city(city, hours=6)

    if forecast is None:
        print("Could not fetch hourly forecast.")
        forecast_alerts = []
    else:
        print("Next 6 hours forecast (temperature & UV index):")
        for t, temp, uv in zip(
            forecast["time"],
            forecast["temperature"],
            forecast["uv_index"],
        ):
            print(f"  {t}: {temp} °C, UV index: {uv}")
        print()  # blank line

        # ---- Forecast-based alerts ----
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

        # ---- Print combined alerts ----
    if not alerts and not forecast_alerts:
        print("No alerts triggered (current or forecast).")
    else:
        print("Alerts (current conditions):")
        if not alerts:
            print("  None.")
        else:
            for alert in alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

        print("\nAlerts (forecast-based):")
        if not forecast_alerts:
            print("  None.")
        else:
            for alert in forecast_alerts:
                print(f"- [{alert.severity.upper()}] {alert.message}")
                print(f"    Reason: {alert.reason}")

    # ---- Email notification (simulated or real depending on config) ----
    send_alerts_email_if_configured(
        city=city,
        weather=weather,
        current_alerts=alerts,
        forecast_alerts=forecast_alerts,
    )
if __name__ == "__main__":
    main()


