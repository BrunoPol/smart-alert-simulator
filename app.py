import os
import json
from typing import Dict, Any, List, Optional
import pandas as pd
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
    st.markdown("#### Select your location")
    st.markdown("*Choose a city to get weather alerts and forecasts*")
    
    preset = st.selectbox(
        "Choose a city",
        ["Lisbon", "Oslo", "Dubai", "Reykjavik", "Custom city"],
        help="Select from preset cities or enter a custom location"
    )
    if preset == "Custom city":
        city = st.text_input(
            "Enter custom city name", 
            value="",
            placeholder="e.g., London, Tokyo, New York"
        )
    else:
        city = preset
    return city.strip()


def build_context_ui() -> Dict[str, Any]:
    """Streamlit UI to build the context dict."""
    st.markdown("#### Choose your household preferences")
    st.markdown("*Select the options that apply to your household for personalized alerts*")

    # Organize checkboxes with nice formatting
    col1, col2 = st.columns(2)
    
    with col1:
        has_pets = st.checkbox(
            "I have pets that spend time outdoors",
            value=False,
            help="For dogs, outdoor cats, or other pets that go outside"
        )
        has_plants = st.checkbox(
            "I have outdoor plants or a garden",
            value=False,
            help="Balcony plants, garden, or outdoor vegetation"
        )
        sensitive_to_cold = st.checkbox(
            "I want cold weather tips",
            value=False,
            help="Extra alerts when temperature drops below 10°C"
        )
        
    with col2:
        sensitive_to_heat = st.checkbox(
            "I want heat weather tips",
            value=False,
            help="Extra alerts when temperature rises above 25°C"
        )
        sensitive_to_pollution = st.checkbox(
            "Someone has breathing problems",
            value=False,
            help="Asthma, COPD, or other respiratory conditions"
        )
        sensitive_to_allergies = st.checkbox(
            "Someone has pollen allergies",
            value=False,
            help="Hay fever or seasonal allergic reactions"
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


def display_alert(alert: Alert) -> None:
    """Display an alert with color coding based on severity."""
    if alert.severity.lower() == "critical":
        st.error(f"**{alert.message}**")
        with st.expander("Alert Details", expanded=False):
            st.caption(f"**Reason:** {alert.reason}")
    elif alert.severity.lower() == "warning":
        st.warning(f"**{alert.message}**")
        with st.expander("Alert Details", expanded=False):
            st.caption(f"**Reason:** {alert.reason}")
    else:  # info
        st.info(f"**{alert.message}**")
        with st.expander("Alert Details", expanded=False):
            st.caption(f"**Reason:** {alert.reason}")


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
    st.markdown("## Smart Alert Simulator Results")
    
    # Configuration summary in collapsible section
    with st.expander("Configuration Summary", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**City:** {city}")
            if notification_email:
                st.write(f"**Email:** {notification_email}")
        with col2:
            active_prefs = sum(1 for v in context.values() if v)
            st.write(f"**Active Preferences:** {active_prefs}/{len(context)}")
            st.write(f"**Forecast Horizon:** {hours} hours")

    if not city:
        st.error("Please enter a city name.")
        return

    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Fetch weather data with progress
    status_text.text("Fetching current weather data...")
    progress_bar.progress(20)

    # ---- Current weather ----
    weather: Optional[dict] = get_current_weather_by_city(city)
    if weather is None:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Could not find weather data for city: {city}")
        return

    progress_bar.progress(40)
    status_text.text("Processing weather data...")

    # Weather display in collapsible section
    with st.expander("Current Weather Details", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Temperature", 
                f"{weather['temperature']}°C",
                delta=f"Feels like {weather.get('apparent_temperature', 'N/A')}°C" if weather.get('apparent_temperature') else None
            )
            
        with col2:
            st.metric("Humidity", f"{weather['humidity']}%")
            
        with col3:
            uv_value = weather.get('uv_index', 'N/A')
            st.metric("UV Index", uv_value)

        # Additional weather details
        st.write("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**Time:** {weather['time']}")
            st.write(f"**Precipitation:** {weather['precipitation']} mm")
            
        with col2:
            st.write(f"**Weather Code:** {weather['weather_code']}")
            if weather.get("wind_speed") is not None:
                st.write(f"**Wind Speed:** {weather['wind_speed']} km/h")

    # ---- Current alerts ----
    progress_bar.progress(50)
    status_text.text("Evaluating current weather alerts...")
    
    current_alerts = evaluate_rules(weather, context=context)

    # ---- Forecast ----
    progress_bar.progress(60)
    status_text.text("Fetching forecast data...")
       
    forecast = get_hourly_forecast_by_city(city, hours=hours)
    if forecast is None:
        st.warning("Could not fetch hourly forecast.")
        forecast_alerts: List[Alert] = []
    else:
        progress_bar.progress(70)
        status_text.text("Processing forecast data...")
        
        with st.expander(f"Next {hours} Hours Forecast", expanded=False):
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
            st.dataframe(df_forecast, use_container_width=True)

            # Temperature chart
            st.markdown("#### Temperature Forecast")
            st.line_chart(df_forecast[["temp (°C)", "feels_like (°C)"]], use_container_width=True)

            # UV & rain chart
            st.markdown("#### UV Index and Rain Chance")
            st.line_chart(df_forecast[["UV index", "rain chance (%)"]], use_container_width=True)

            # Wind chart
            st.markdown("#### Wind Speed")
            st.line_chart(df_forecast[["wind (km/h)"]], use_container_width=True)

        # Keep using the same rules engine
        forecast_alerts = evaluate_forecast_rules(forecast, context=context)

    # ---- Air quality & pollen ----
    progress_bar.progress(80)
    status_text.text("Fetching air quality and pollen data...")
    
    air_quality_alerts: List[Alert] = []
    air_quality_summary_dict: Optional[Dict[str, str]] = None

    air_quality = get_air_quality_by_city(city, hours=hours)
    if air_quality is None:
        st.warning("Could not fetch air quality / pollen data.")
    else:
        progress_bar.progress(90)
        status_text.text("Processing air quality data...")
        
        with st.expander("Air Quality & Pollen Data", expanded=False):
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

            # Air quality metrics
            col1, col2 = st.columns(2)
            with col1:
                if max_pm25 is not None:
                    st.metric("Max PM2.5", f"{max_pm25} µg/m³")
                    st.caption(f"Peak at {max_pm25_time}")
                    
            with col2:
                if max_pm10 is not None:
                    st.metric("Max PM10", f"{max_pm10} µg/m³") 
                    st.caption(f"Peak at {max_pm10_time}")

            # Pollen information
            pollen_candidates = [
                ("grass", max_grass, max_grass_time),
                ("birch", max_birch, max_birch_time),
                ("ragweed", max_ragweed, max_ragweed_time),
            ]
            pollen_candidates = [(n, v, t) for (n, v, t) in pollen_candidates if v is not None]
            if pollen_candidates:
                name, val, t = max(pollen_candidates, key=lambda x: x[1])
                st.metric("Highest Pollen", f"{name.title()}: {val}")
                st.caption(f"Peak at {t}")
                pollen_summary_str = f"{name} = {val} at {t}"
            else:
                st.info("Pollen data: Not available")
                pollen_summary_str = "n/a"

            air_quality_summary_dict = {
                "Max PM2.5": f"{max_pm25} at {max_pm25_time}" if max_pm25 is not None else "n/a",
                "Max PM10": f"{max_pm10} at {max_pm10_time}" if max_pm10 is not None else "n/a",
                "Max pollen": pollen_summary_str,
            }

        air_quality_alerts = evaluate_air_quality_rules(air_quality, context=context)

    # Complete progress
    progress_bar.progress(100)
    status_text.text("Analysis complete!")
    
    # Clear progress indicators after a short delay
    import time
    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()

    # ---- Show alerts with color coding ----
    st.markdown("## Alert Summary")
    
    # Current condition alerts
    with st.expander("Current Weather Alerts", expanded=True):
        if not current_alerts:
            st.success("No current weather alerts")
        else:
            for alert in current_alerts:
                display_alert(alert)

    # Future alerts (forecast + air quality)
    combined_future = list(forecast_alerts) + list(air_quality_alerts)
    with st.expander("Forecast & Air Quality Alerts", expanded=True):
        if not combined_future:
            st.success("No forecast or air quality alerts")
        else:
            for alert in combined_future:
                display_alert(alert)

    # ---- Email sending ----
    if notification_email:
        with st.expander("Email Notification", expanded=False):
            st.info("Sending alert summary via email...")
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
        st.info("Add an email address to receive notifications for future runs.")


# --- Streamlit main app ---

def main():
    st.title("Smart Alert Simulator")
    st.markdown("*Personalized weather, air quality, and pollen alerts for your location*")
    
    st.markdown("---")
    st.header("Configuration")

    # Location selection in collapsible section
    with st.expander("Location Settings", expanded=True):
        city = choose_city_ui()

    # Household preferences in collapsible section  
    with st.expander("Household Preferences", expanded=True):
        context = build_context_ui()

    # Email and notification settings
    with st.expander("Email & Notification Settings", expanded=False):
        notification_email = st.text_input(
            "Email address (for this run and optionally daily alerts)",
            value="",
            placeholder="your.email@example.com"
        ).strip() or None

        register_daily = st.checkbox(
            "Register this email for daily alert emails from the server",
            help="You'll receive one alert summary per day based on your preferences"
        )

    # Advanced settings
    with st.expander("Advanced Settings", expanded=False):
        hours = st.slider(
            "Forecast horizon (hours)",
            min_value=3,
            max_value=24,
            value=6,
            step=3,
            help="How many hours ahead to analyze for forecast alerts"
        )

    # Run button with enhanced styling
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        run_button = st.button(
            "Run Smart Alert Simulator", 
            type="primary",
            use_container_width=True
        )

    # Handle button click
    if run_button:
        if not city:
            st.error("Please choose or enter a city name.")
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
                st.error("You enabled daily alerts but no email was provided.")
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
                    st.success(f"Updated existing profile for {notification_email}")
                    break
            else:
                profiles.append(profile)
                st.success(f"Added new profile for {notification_email}")

            save_profiles(profiles)
            sync_profile_to_server(profile)

            st.info(
                "This profile will be used by the server to send daily alert emails."
            )


if __name__ == "__main__":
    main()
