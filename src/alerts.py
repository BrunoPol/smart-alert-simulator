"""Email and notification helpers for the Smart Alert Simulator."""

import os
from typing import Iterable, Optional

from email.message import EmailMessage
import smtplib

from dotenv import load_dotenv

from src.rules_engine import Alert

# Load environment variables from .env
load_dotenv()


def _build_alerts_email_body(
    city: str,
    weather: dict,
    current_alerts: Iterable[Alert],
    forecast_alerts: Iterable[Alert],
    air_quality_alerts: Iterable[Alert] | None = None,
    air_quality_summary: dict | None = None,
    forecast_lines: list[str] | None = None,
) -> str:
    """Create a plain-text email body describing the alerts."""

    current_alerts = list(current_alerts)
    forecast_alerts = list(forecast_alerts)
    air_quality_alerts = list(air_quality_alerts or [])

    lines: list[str] = []

    lines.append(f"Smart Alert Simulator - Alerts for {city}")
    lines.append("")
    lines.append("Current weather:")
    lines.append(f"  Time:        {weather.get('time')}")
    lines.append(f"  Temperature: {weather.get('temperature')} °C")
    if weather.get("apparent_temperature") is not None:
        lines.append(f"  Feels like:  {weather.get('apparent_temperature')} °C")
    lines.append(f"  Humidity:    {weather.get('humidity')} %")
    lines.append(f"  Precip:      {weather.get('precipitation')} mm")
    lines.append(f"  Code:        {weather.get('weather_code')}")
    if weather.get("uv_index") is not None:
        lines.append(f"  UV index:    {weather.get('uv_index')}")
    if weather.get("wind_speed") is not None:
        lines.append(f"  Wind:        {weather.get('wind_speed')} km/h")
    lines.append("")

    # --- Short-term forecast snapshot (optional) ---
    if forecast_lines:
        lines.append("Short-term forecast (next hours):")
        for line in forecast_lines:
            lines.append(f"  {line}")
        lines.append("")

    # --- Current alerts ---
    lines.append("Alerts (current conditions):")
    if not current_alerts:
        lines.append("  None.")
    else:
        for alert in current_alerts:
            lines.append(f"- [{alert.severity.upper()}] {alert.message}")
            lines.append(f"    Reason: {alert.reason}")
    lines.append("")

    # --- Forecast alerts ---
    lines.append("Alerts (forecast-based):")
    if not forecast_alerts:
        lines.append("  None.")
    else:
        for alert in forecast_alerts:
            lines.append(f"- [{alert.severity.upper()}] {alert.message}")
            lines.append(f"    Reason: {alert.reason}")
    lines.append("")

    # --- Air quality / pollen summary ---
    if air_quality_summary:
        lines.append("Air quality & pollen summary:")
        for key, val in air_quality_summary.items():
            lines.append(f"  {key}: {val}")
        lines.append("")

    # --- Air quality / pollen alerts ---
    if air_quality_alerts:
        lines.append("Alerts (air quality / pollen):")
        for alert in air_quality_alerts:
            lines.append(f"- [{alert.severity.upper()}] {alert.message}")
            lines.append(f"    Reason: {alert.reason}")
        lines.append("")
    else:
        lines.append("No air quality/pollen alerts detected.")
        lines.append("")

    lines.append("This message was generated automatically by the Smart Alert Simulator.")
    return "\n".join(lines)


def _send_email(subject: str, body: str, email_to_override: Optional[str] = None) -> None:
    """
    Low-level email sender using SMTP.
    Respects EMAIL_ENABLED flag in environment.
    Allows overriding the recipient email address.
    """

    enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

    smtp_server = os.getenv("EMAIL_SMTP_SERVER")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    username = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", username or "")
    email_to_env = os.getenv("EMAIL_TO")
    email_to = email_to_override or email_to_env

    if not enabled:
        print("Email notifications are disabled (EMAIL_ENABLED is not 'true').")
        print("---- Simulated email ----")
        print(f"Subject: {subject}")
        print(body)
        print("---- End of simulated email ----")
        return

    if not (smtp_server and username and password and email_from and email_to):
        print("Email configuration is incomplete. Cannot send email.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        print("Email sent successfully.")
    except Exception as exc:
        print(f"Failed to send email: {exc}")


def send_alerts_email_if_configured(
    city: str,
    weather: dict,
    current_alerts: Iterable[Alert],
    forecast_alerts: Iterable[Alert],
    air_quality_alerts: Iterable[Alert] | None = None,
    air_quality_summary: dict | None = None,
    forecast_lines: list[str] | None = None,
    email_to: Optional[str] = None,
) -> None:

    """
    High-level helper:
    - If there are no alerts at all, do nothing.
    - Otherwise, build an email and send it (or simulate it).
    - If email_to is provided, it overrides EMAIL_TO from environment.
    """

    current_alerts = list(current_alerts)
    forecast_alerts = list(forecast_alerts)
    air_quality_alerts = list(air_quality_alerts or [])

    # If absolutely nothing triggered, skip email
    if not current_alerts and not forecast_alerts and not air_quality_alerts:
        print("No alerts to email. Skipping email notification.")
        return

    subject = f"Smart Alert Simulator - Alerts for {city}"
    body = _build_alerts_email_body(
        city=city,
        weather=weather,
        current_alerts=current_alerts,
        forecast_alerts=forecast_alerts,
        air_quality_alerts=air_quality_alerts,
        air_quality_summary=air_quality_summary,
        forecast_lines=forecast_lines,
    )

    _send_email(subject, body, email_to_override=email_to)


