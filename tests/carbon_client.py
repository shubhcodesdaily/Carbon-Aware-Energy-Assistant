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