"""
Tiny profile API for Smart Alert Simulator.

Exposes a single endpoint:

    POST /register_profile

Body (JSON):
{
  "email": "...",
  "city": "...",
  "has_pets": true/false,
  "has_plants": true/false,
  "sensitive_to_cold": true/false,
  "sensitive_to_heat": true/false,
  "api_key": "shared-secret"
}

If api_key matches PROFILE_API_SECRET in .env, the profile is
added/updated in config/user_profiles.json on the server.
"""

import json
import os
from typing import Any, Dict, List

from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables from .env (on PythonAnywhere and locally)
load_dotenv()

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "user_profiles.json")

PROFILE_API_SECRET = os.getenv("PROFILE_API_SECRET")


def load_profiles() -> List[Dict[str, Any]]:
    """Load all user profiles from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return []

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    return data


def save_profiles(profiles: List[Dict[str, Any]]) -> None:
    """Save all user profiles to the JSON file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)


@app.route("/register_profile", methods=["POST"])
def register_profile() -> Any:
    """
    Register or update a user profile.

    Requires a JSON body with the expected fields and a matching api_key.
    """
    if PROFILE_API_SECRET is None:
        return jsonify({"error": "Server not configured with PROFILE_API_SECRET"}), 500

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    api_key = payload.get("api_key")
    if api_key != PROFILE_API_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    email = payload.get("email")
    city = payload.get("city")
    if not email or not city:
        return jsonify({"error": "Missing 'email' or 'city'"}), 400

    profile = {
        "email": email,
        "city": city,
        "has_pets": bool(payload.get("has_pets", False)),
        "has_plants": bool(payload.get("has_plants", False)),
        "sensitive_to_cold": bool(payload.get("sensitive_to_cold", False)),
        "sensitive_to_heat": bool(payload.get("sensitive_to_heat", False)),
    }

    profiles = load_profiles()

    # upsert by email
    for i, existing in enumerate(profiles):
        if existing.get("email") == email:
            profiles[i] = profile
            break
    else:
        profiles.append(profile)

    save_profiles(profiles)

    return jsonify({"status": "ok", "profile": profile}), 200


# For local testing only:
if __name__ == "__main__":
    app.run(debug=True)
