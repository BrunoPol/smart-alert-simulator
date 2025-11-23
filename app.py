import os
import json
from typing import Dict, Any, List, Optional
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import streamlit as st
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
    Alert,
)
from src.alerts import send_alerts_email_if_configured

# --- Config / environment ---

load_dotenv()

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "user_profiles.json")

PROFILE_API_URL = os.getenv("PROFILE_API_URL")
PROFILE_API_SECRET = os.getenv("PROFILE_API_SECRET")


# --- Helper functions (similar to cli.py, but without input()/print() ---

def load_profiles() -> List[Dict[str, Any]]:
    """Load all user profiles from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return []

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        st.warning(f"Warning: could not parse {CONFIG_PATH}: {exc}")
        return []

    if not isinstance(data, list):
        st.warning(f"Warning: expected a list of profiles in {CONFIG_PATH}.")
        return []

    return data


def save_profiles(profiles: List[Dict[str, Any]]) -> None:
    """Save all user profiles to the JSON file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    st.info(f"Profiles saved to {CONFIG_PATH}.")


def sync_profile_to_server(profile: Dict[str, Any]) -> None:
    """Send the profile to the server's /register_profile API (best-effort)."""
    if not PROFILE_API_URL or not PROFILE_API_SECRET:
        st.info("PROFILE_API_URL or PROFILE_API_SECRET not set; skipping server sync.")
        return

    payload = dict(profile)
    payload["api_key"] = PROFILE_API_SECRET

    try:
        resp = requests.post(PROFILE_API_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            st.success("Profile synced to server successfully.")
        else:
            st.warning(f"Server sync failed: {resp.status_code} {resp.text}")
    except Exception as exc:
        st.warning(f"Could not sync profile to server: {exc}")


def choose_city_ui() -> str:
    """Streamlit UI for choosing a city."""
    preset = st.selectbox(
        "Choose a city",
        ["Lisbon", "Oslo", "Dubai", "Reykjavik", "Custom city"],
    )
    if preset == "Custom city":
        city = st.text_input("Enter custom city name", value="")
    else:
        city = preset
    return city.strip()


def build_context_ui() -> Dict[str, Any]:
    """Streamlit UI to build the context dict."""
    st.subheader("Household profile")

    has_pets = st.checkbox(
        "I have pets that spend time outdoors (for example dogs or outdoor cats).",
        value=False,
    )
    has_plants = st.checkbox(
        "I have outdoor plants, balcony plants, or a garden.",
        value=False,
    )
    sensitive_to_cold = st.checkbox(
        "I would like extra tips when it’s cold outside (e.g. below 10°C).",
        value=False,
    )
    sensitive_to_heat = st.checkbox(
        "I would like extra tips when it’s hot outside (e.g. above 25°C).",
        value=False,
    )
    sensitive_to_pollution = st.checkbox(
        "Someone in my household has asthma or other breathing problems.",
        value=False,
    )
    sensitive_to_allergies = st.checkbox(
        "Someone in my household has pollen allergies (hay fever).",
        value=False,
    )

    context = {
        "has_pets": has_pets,
        "has_plants": has_plants,
        "sensitive_to_cold": sensitive_to_cold,
        "sensitive_to_heat": sensitive_to_heat,
        "sensitive_to_pollution": sensitive_to_pollution,
        "sensitive_to_allergies": sensitive_to_allergies,
    }

    return context


def run_alert_flow_streamlit(
    city: str,
    context: Dict[str, Any],
    notification_email: Optional[str],
    hours: int = 6,
) -> None:
    """
    Run the full alert flow and display results in Streamlit.
    Mirrors cli.run_alert_flow but uses st.write/st.table instead of print().
    """
    st.markdown("## Run Smart Alert Simulator")
    st.write(f"**City:** {city}")
    st.write("**Context:**")
    st.json(context)
    if notification_email:
        st.write(f"**Notification email:** {notification_email}")

    if not city:
        st.error("Please enter a city name.")
        return

    # ---- Current weather ----
    weather: Optional[dict] = get_current_weather_by_city(city)
    if weather is None:
        st.error(f"Could not find weather data for city: {city}")
        return

    st.subheader("Current weather")
    st.write(f"Time: {weather['time']}")
    st.write(f"Temperature: {weather['temperature']} °C")
    if weather.get("apparent_temperature") is not None:
        st.write(f"Feels like: {weather['apparent_temperature']} °C")
    st.write(f"Humidity: {weather['humidity']} %")
    st.write(f"Precipitation: {weather['precipitation']} mm")
    st.write(f"Weather code: {weather['weather_code']}")
    if weather.get("uv_index") is not None:
        st.write(f"UV index: {weather['uv_index']}")
    if weather.get("wind_speed") is not None:
        st.write(f"Wind: {weather['wind_speed']} km/h")

    # ---- Current alerts ----
    current_alerts = evaluate_rules(weather, context=context)

    # ---- Forecast ----
       
    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        st.warning("Could not fetch hourly forecast.")
        forecast_alerts: List[Alert] = []
    else:
        st.subheader(f"Next {hours} hours forecast")

        times = forecast.get("time", [])
        temps = forecast.get("temperature", [])
        app_temps = forecast.get("apparent_temperature") or [None] * len(times)
        uvs = forecast.get("uv_index") or [None] * len(times)
        probs = forecast.get("precipitation_probability") or [None] * len(times)
        winds = forecast.get("wind_speed") or [None] * len(times)

        # Build a DataFrame for easier plotting
        df_forecast = pd.DataFrame(
            {
                "time": pd.to_datetime(times),
                "temp (°C)": temps,
                "feels_like (°C)": app_temps,
                "UV index": uvs,
                "rain chance (%)": probs,
                "wind (km/h)": winds,
            }
        ).set_index("time")

        # Show table (so your professor can inspect exact values)
        st.dataframe(df_forecast)

        # Temperature chart
        st.markdown("#### Temperature (next hours)")
        st.line_chart(df_forecast[["temp (°C)", "feels_like (°C)"]])

        # UV & rain chart
        st.markdown("#### UV index and rain chance")
        st.line_chart(df_forecast[["UV index", "rain chance (%)"]])

        # Optional: wind chart
        st.markdown("#### Wind speed")
        st.line_chart(df_forecast[["wind (km/h)"]])

        # Keep using the same rules engine
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)


    # ---- Air quality & pollen ----
    air_quality_alerts: List[Alert] = []
    air_quality_summary_dict: Optional[Dict[str, str]] = None

    air_quality = get_air_quality_by_city(city, hours=hours)
    if air_quality is None:
        st.warning("Could not fetch air quality / pollen data.")
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

        st.subheader("Air quality & pollen (summary)")
        if max_pm25 is not None:
            st.write(f"Max PM2.5: {max_pm25} at {max_pm25_time}")
        if max_pm10 is not None:
            st.write(f"Max PM10: {max_pm10} at {max_pm10_time}")

        pollen_candidates = [
            ("grass", max_grass, max_grass_time),
            ("birch", max_birch, max_birch_time),
            ("ragweed", max_ragweed, max_ragweed_time),
        ]
        pollen_candidates = [(n, v, t) for (n, v, t) in pollen_candidates if v is not None]
        if pollen_candidates:
            name, val, t = max(pollen_candidates, key=lambda x: x[1])
            st.write(f"Max pollen: {name} = {val} at {t}")
            pollen_summary_str = f"{name} = {val} at {t}"
        else:
            st.write("Pollen data: n/a")
            pollen_summary_str = "n/a"

        air_quality_summary_dict = {
            "Max PM2.5": f"{max_pm25} at {max_pm25_time}" if max_pm25 is not None else "n/a",
            "Max PM10": f"{max_pm10} at {max_pm10_time}" if max_pm10 is not None else "n/a",
            "Max pollen": pollen_summary_str,
        }

        air_quality_alerts = evaluate_air_quality_rules(air_quality, context=context)

    # ---- Show alerts ----
    st.subheader("Alerts (current conditions)")
    if not current_alerts:
        st.info("No current-condition alerts.")
    else:
        for alert in current_alerts:
            st.write(f"- **[{alert.severity.upper()}]** {alert.message}")
            st.caption(f"Reason: {alert.reason}")

    combined_future = list(forecast_alerts) + list(air_quality_alerts)
    st.subheader("Alerts (forecast & air quality / pollen)")
    if not combined_future:
        st.info("No forecast or air-quality alerts.")
    else:
        for alert in combined_future:
            st.write(f"- **[{alert.severity.upper()}]** {alert.message}")
            st.caption(f"Reason: {alert.reason}")

    # ---- Email sending ----
    if notification_email:
        st.subheader("Email notification")
        send_alerts_email_if_configured(
            city=city,
            weather=weather,
            current_alerts=current_alerts,
            forecast_alerts=forecast_alerts,
            air_quality_alerts=air_quality_alerts,
            air_quality_summary=air_quality_summary_dict,
            email_to=notification_email,
        )
    else:
        st.info("No notification email provided for this run.")


# --- Streamlit main app ---

def main():
    st.title("Smart Alert Simulator")
    st.write("Personalized weather, air quality, and pollen alerts.")

    st.header("Configure your run")

    # --- Location ---
    city = choose_city_ui()

    # --- Household context ---
    context = build_context_ui()

    # --- Email for this run / registration ---
    notification_email = st.text_input(
        "Email address (used for this run, and optionally for daily alerts)",
        value="",
    ).strip() or None

    # --- Option to register for daily email alerts ---
    register_daily = st.checkbox(
        "Also register / update this email for daily alert emails (once per day from the server)."
    )

    # --- Forecast horizon ---
    hours = st.slider(
        "Forecast horizon (hours)",
        min_value=3,
        max_value=24,
        value=6,
        step=3,
    )

    # --- Run button ---
    if st.button("Run simulator"):
        if not city:
            st.error("Please choose or enter a city.")
            return

        # 1) Run the simulator once (same as before)
        run_alert_flow_streamlit(
            city=city,
            context=context,
            notification_email=notification_email,
            hours=hours,
        )

        # 2) Optionally register for daily emails
        if register_daily:
            if not notification_email:
                st.error("You checked registration for daily alerts, but no email was provided.")
                return

            profile = {
                "email": notification_email,
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
                if existing.get("email") == notification_email:
                    profiles[i] = profile
                    st.success(f"Updated existing profile for {notification_email}.")
                    break
            else:
                profiles.append(profile)
                st.success(f"Added new profile for {notification_email}.")

            save_profiles(profiles)
            sync_profile_to_server(profile)

            st.info(
                "This profile will be used by the server (PythonAnywhere) to send daily alert emails."
            )


if __name__ == "__main__":
    main()
