"""Client for UK wholesale power prices from Elexon's BMRS Insights API.

Docs: https://developer.data.elexon.co.uk  (open data, GB only, no key needed
for most Insights endpoints). All timestamps are UTC.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from src.energyagent.tools.carbon_logic import Slot

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
SLOT_MINUTES = 30


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def get_market_index_price(hours: int = 48) -> dict:
    """Fetch Market Index (wholesale) price for a window around now."""
    now = datetime.now(timezone.utc)
    params = {
        "from": _iso(now - timedelta(hours=hours)),
        "to": _iso(now + timedelta(hours=hours)),
    }
    url = f"{BASE_URL}/balancing/pricing/market-index"
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _coerce_start(record: dict) -> datetime | None:
    for key in ("startTime", "start", "settlementPeriodStartTime"):
        val = record.get(key)
        if val:
            text = str(val).replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _coerce_price(record: dict) -> float | None:
    for key in ("price", "marketIndexPrice", "value", "systemBuyPrice"):
        if record.get(key) is not None:
            try:
                return float(record[key])
            except (TypeError, ValueError):
                continue
    return None


def parse_price_series(payload: dict) -> list[Slot]:
    """Turn an Elexon price payload into Slot objects (price stored in
    `intensity` so the shared window logic can operate on it)."""
    rows = payload.get("data", payload if isinstance(payload, list) else [])
    by_start: dict[datetime, Slot] = {}
    for record in rows:
        start = _coerce_start(record)
        price = _coerce_price(record)
        if start is None or price is None:
            continue
        end = start + timedelta(minutes=SLOT_MINUTES)
        by_start[start] = Slot(start=start, end=end, intensity=price, index=None)
    return sorted(by_start.values(), key=lambda s: s.start)