"""Client for the National Grid / NESO Carbon Intensity API.

Docs: https://api.carbonintensity.org.uk  (free, no API key, GB only).
All timestamps the API returns are UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

BASE_URL = "https://api.carbonintensity.org.uk"


def get_current_intensity() -> dict:
    """National carbon intensity for the current half-hour."""
    response = requests.get(f"{BASE_URL}/intensity", timeout=10)
    response.raise_for_status()
    return response.json()

def _now_iso() -> str:
    """Current time in the API's expected 'YYYY-MM-DDThh:mmZ' format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def get_national_forecast_48h() -> dict:
    """National carbon-intensity forecast for the next 48 hours (half-hourly)."""
    url = f"{BASE_URL}/intensity/{_now_iso()}/fw48h"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()    

def get_generation_mix() -> dict:
    """Current national fuel mix (wind, gas, nuclear, etc.), as percentages."""
    response = requests.get(f"{BASE_URL}/generation", timeout=10)
    response.raise_for_status()
    return response.json()


def get_regional_forecast_48h(postcode: str) -> dict:
    """48-hour forecast localised to a GB outward postcode (e.g. 'CV1').

    Only the outward part of the postcode is used, per the API's rules.
    """
    outcode = postcode.strip().split()[0].upper() if postcode.strip() else ""
    if not outcode:
        raise ValueError("A postcode is required for the regional forecast.")
    url = f"{BASE_URL}/regional/intensity/{_now_iso()}/fw48h/postcode/{outcode}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()