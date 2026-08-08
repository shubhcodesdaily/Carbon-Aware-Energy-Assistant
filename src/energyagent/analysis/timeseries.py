"""Turn a stream of half-hourly grid readings into analysis: an hour-of-day
profile, peak/off-peak structure, and anomaly flags.

Kept dependency-light: stdlib `csv` to append to the log, pandas to analyse.
Everything is deterministic and unit-tested against fixed inputs.
"""

from __future__ import annotations

import csv
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.energyagent.tools.carbon_logic import Slot

UK_TZ = ZoneInfo("Europe/London")
LOG_HEADER = ["start_utc", "value"]


# ---------- collecting ----------

def slots_to_frame(slots: list[Slot]) -> pd.DataFrame:
    """List[Slot] -> tidy frame with a UK hour-of-day column."""
    rows = [
        {"start_utc": s.start, "value": s.intensity}
        for s in slots
        if s.intensity is not None
    ]
    df = pd.DataFrame(rows, columns=["start_utc", "value"])
    return _add_hour(df)


def append_slots_to_log(slots: list[Slot], path: str | Path) -> int:
    """Append readings to a CSV log (creates it with a header if new).

    Returns the number of rows written. Designed to be called on a schedule so
    a real, growing time-series accumulates over days/weeks.
    """
    path = Path(path)
    new = path.exists() is False
    written = 0
    with path.open("a", newline="") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(LOG_HEADER)
        for s in slots:
            if s.intensity is None:
                continue
            writer.writerow([s.start.isoformat(), s.intensity])
            written += 1
    return written


def load_log(path: str | Path) -> pd.DataFrame:
    """Load a CSV log written by `append_slots_to_log` into an analysis frame."""
    df = pd.read_csv(path)
    df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
    return _add_hour(df)


def _add_hour(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df["hour_uk"] = pd.Series(dtype="int64")
        return df
    local = df["start_utc"].dt.tz_convert(UK_TZ)
    df = df.copy()
    df["hour_uk"] = local.dt.hour
    return df


# ---------- analysis ----------

def hour_of_day_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Mean / std / count of the metric for each UK hour (0-23)."""
    prof = (
        df.groupby("hour_uk")["value"]
        .agg(mean="mean", std="std", count="count")
        .reset_index()
    )
    prof["std"] = prof["std"].fillna(0.0)
    return prof


def peak_offpeak_summary(df: pd.DataFrame) -> dict:
    """Cheapest/greenest and most expensive/dirtiest hours in the profile."""
    prof = hour_of_day_profile(df)
    if prof.empty:
        return {}
    lo = prof.loc[prof["mean"].idxmin()]
    hi = prof.loc[prof["mean"].idxmax()]
    return {
        "best_hour": int(lo["hour_uk"]),
        "best_mean": round(float(lo["mean"]), 1),
        "worst_hour": int(hi["hour_uk"]),
        "worst_mean": round(float(hi["mean"]), 1),
        "spread": round(float(hi["mean"] - lo["mean"]), 1),
    }


def detect_anomalies(df: pd.DataFrame, z: float = 2.0) -> pd.DataFrame:
    """Flag readings that deviate more than `z` std devs from their own
    hour-of-day mean — i.e. an unusual spike/dip for that time of day, the kind
    of dislocation worth a second look.

    Returns the flagged rows with `expected`, `deviation` and `z_score`.
    """
    prof = hour_of_day_profile(df).set_index("hour_uk")
    merged = df.join(prof, on="hour_uk", rsuffix="_prof")
    # Guard against zero-variance hours (no anomaly possible there).
    std = merged["std"].replace(0.0, pd.NA)
    merged["z_score"] = (merged["value"] - merged["mean"]) / std
    merged["expected"] = merged["mean"].round(1)
    merged["deviation"] = (merged["value"] - merged["mean"]).round(1)
    flagged = merged[merged["z_score"].abs() >= z].copy()
    flagged["z_score"] = flagged["z_score"].round(2)
    cols = ["start_utc", "hour_uk", "value", "expected", "deviation", "z_score"]
    return flagged[cols].sort_values("start_utc").reset_index(drop=True)