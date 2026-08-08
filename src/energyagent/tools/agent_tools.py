"""Tools the LLM agent can call. Each returns a short, human-readable string
that gets fed back into the agent's reasoning.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.energyagent.tools import carbon_client, price_client
from src.energyagent.tools.carbon_logic import (
    describe_generation_mix,
    describe_window,
    find_greenest_window,
    parse_forecast,
    parse_generation_mix,
)
from src.energyagent.tools.price_client import parse_price_series


@tool
def get_current_carbon_intensity() -> str:
    """Get Great Britain's electricity carbon intensity right now (gCO2/kWh and band).

    Use this when the user asks how clean or dirty the grid is at the moment.
    """
    try:
        payload = carbon_client.get_current_intensity()
        block = payload["data"][0]["intensity"]
        value = block.get("actual") or block.get("forecast")
        index = block.get("index", "unknown")
        return f"Current GB carbon intensity is about {value} gCO2/kWh (index: {index})."
    except Exception as exc:
        return f"Could not fetch current intensity: {exc}"


@tool
def get_supply_mix() -> str:
    """Get Great Britain's current electricity generation (fuel) mix.

    Use this when the user asks what is powering the grid right now, or how much
    is coming from wind/gas/nuclear/renewables - the supply side of the market.
    """
    try:
        payload = carbon_client.get_generation_mix()
        mix = parse_generation_mix(payload)
        return describe_generation_mix(mix)
    except Exception as exc:
        return f"Could not fetch the generation mix: {exc}"


@tool
def find_greenest_time_window(hours: float, postcode: str = "") -> str:
    """Find the greenest (lowest-carbon) time window in the next 48 hours.

    Args:
        hours: How long the activity takes, in hours (e.g. 2 for a 2-hour wash).
        postcode: Optional GB outward postcode (e.g. "CV1") for a regional
            forecast. Leave empty for the national forecast.
    """
    try:
        if postcode.strip():
            payload = carbon_client.get_regional_forecast_48h(postcode)
        else:
            payload = carbon_client.get_national_forecast_48h()
        slots = parse_forecast(payload)
        window = find_greenest_window(slots, hours=hours)
        scope = f"in {postcode.upper()}" if postcode.strip() else "nationally (GB)"
        return f"{describe_window(window, hours=hours)} (Forecast {scope}.)"
    except Exception as exc:
        return f"Could not compute the greenest window: {exc}"


@tool
def find_cheapest_time_window(hours: float) -> str:
    """Find the cheapest (lowest wholesale price) time window from recent GB
    Market Index prices.

    Args:
        hours: How long the activity takes, in hours.
    """
    try:
        payload = price_client.get_market_index_price(hours=48)
        slots = parse_price_series(payload)
        window = find_greenest_window(slots, hours=hours)
        return describe_window(window, hours=hours, unit="GBP/MWh")
    except Exception as exc:
        return f"Could not compute the cheapest window: {exc}"


TOOLS = [
    get_current_carbon_intensity,
    get_supply_mix,
    find_greenest_time_window,
    find_cheapest_time_window,
]