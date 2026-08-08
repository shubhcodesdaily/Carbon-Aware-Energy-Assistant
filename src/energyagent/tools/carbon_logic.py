"""Core analytical logic for GB grid data: parsing, window optimisation, and
the generation (fuel) mix. No network here — everything operates on already
-fetched payloads so it stays fast and unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")
SLOT_MINUTES = 30

RENEWABLE_FUELS = {"wind", "solar", "hydro"}
LOW_CARBON_FUELS = RENEWABLE_FUELS | {"nuclear", "biomass"}


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    intensity: int | None
    index: str | None

    @property
    def start_uk(self) -> datetime:
        return self.start.astimezone(UK_TZ)

    @property
    def end_uk(self) -> datetime:
        return self.end.astimezone(UK_TZ)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    avg_value: float
    slots: list[Slot]

    @property
    def start_uk(self) -> datetime:
        return self.start.astimezone(UK_TZ)

    @property
    def end_uk(self) -> datetime:
        return self.end.astimezone(UK_TZ)


def _parse_iso_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def slots_for_duration(hours: float) -> int:
    if hours <= 0:
        raise ValueError("Duration must be positive.")
    return max(1, math.ceil(hours * 60 / SLOT_MINUTES))


def parse_forecast(payload: dict) -> list[Slot]:
    data = payload.get("data", [])
    if isinstance(data, dict):
        data = data.get("data", [])
    slots: list[Slot] = []
    for entry in data:
        block = entry.get("intensity", {}) or {}
        value = block.get("actual")
        if value is None:
            value = block.get("forecast")
        slots.append(Slot(
            start=_parse_iso_utc(entry["from"]),
            end=_parse_iso_utc(entry["to"]),
            intensity=value,
            index=block.get("index"),
        ))
    return slots


def find_greenest_window(slots: list[Slot], hours: float) -> Window:
    if not slots:
        raise ValueError("No forecast slots supplied.")
    ordered = sorted(slots, key=lambda s: s.start)
    width = slots_for_duration(hours)
    if width > len(ordered):
        raise ValueError(
            f"Requested {hours}h ({width} slots) but only {len(ordered)} available.")
    best: Window | None = None
    for i in range(len(ordered) - width + 1):
        block = ordered[i:i + width]
        if any(s.intensity is None for s in block):
            continue
        avg = sum(s.intensity for s in block) / width
        if best is None or avg < best.avg_value:
            best = Window(start=block[0].start, end=block[-1].end,
                          avg_value=avg, slots=block)
    if best is None:
        raise ValueError("No window with complete intensity data was found.")
    return best


def index_for_intensity(intensity: float) -> str:
    if intensity < 35:
        return "very low"
    if intensity < 100:
        return "low"
    if intensity < 200:
        return "moderate"
    if intensity < 290:
        return "high"
    return "very high"


def describe_window(window: Window, hours: float, unit: str = "gCO2/kWh") -> str:
    start = window.start_uk.strftime("%a %d %b, %H:%M")
    end = window.end_uk.strftime("%H:%M")
    if unit == "gCO2/kWh":
        tail = f" (index: {index_for_intensity(window.avg_value)})"
    else:
        tail = ""
    return (f"Best {hours:g}h window: {start}-{end} UK time, "
            f"averaging {window.avg_value:.0f} {unit}{tail}.")


# ---- generation (fuel) mix ----

def parse_generation_mix(payload: dict) -> dict[str, float]:
    data = payload.get("data", {}) or {}
    mix = data.get("generationmix", []) or []
    out: dict[str, float] = {}
    for item in mix:
        fuel = str(item.get("fuel", "")).lower()
        if fuel:
            out[fuel] = float(item.get("perc", 0.0))
    return out


def renewable_share(mix: dict[str, float]) -> float:
    return round(sum(p for f, p in mix.items() if f in RENEWABLE_FUELS), 1)


def low_carbon_share(mix: dict[str, float]) -> float:
    return round(sum(p for f, p in mix.items() if f in LOW_CARBON_FUELS), 1)


def describe_generation_mix(mix: dict[str, float], top_n: int = 4) -> str:
    if not mix:
        return "No generation-mix data available."
    ranked = sorted(mix.items(), key=lambda kv: kv[1], reverse=True)
    lead = ", ".join(f"{fuel} {perc:.0f}%" for fuel, perc in ranked[:top_n])
    return (f"Current GB supply mix: {lead}. "
            f"Renewables {renewable_share(mix):.0f}%, "
            f"low-carbon {low_carbon_share(mix):.0f}%.")