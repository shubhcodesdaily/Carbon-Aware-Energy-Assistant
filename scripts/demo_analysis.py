"""End-to-end demo of the analysis pipeline WITHOUT hitting the live APIs.

Generates a realistic synthetic week of half-hourly carbon-intensity data (with
a daily shape and a couple of injected spikes), logs it, analyses it, and writes
an Excel report. Run:  python scripts/demo_analysis.py
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.energyagent.tools.carbon_logic import Slot
from src.energyagent.analysis.timeseries import (
    append_slots_to_log, load_log, peak_offpeak_summary, detect_anomalies,
)
from src.energyagent.analysis.excel_report import build_excel_report

random.seed(7)


def synthetic_week() -> list[Slot]:
    """A week of half-hourly slots: low overnight, high in the evening peak."""
    start = datetime(2026, 1, 12, 0, 0, tzinfo=timezone.utc)
    slots: list[Slot] = []
    for i in range(48 * 7):
        t = start + timedelta(minutes=30 * i)
        hour = t.hour + t.minute / 60
        # Daily curve: trough ~04:00, peak ~18:00.
        base = 160 + 90 * math.sin((hour - 10) / 24 * 2 * math.pi)
        value = max(20, base + random.gauss(0, 12))
        slots.append(Slot(start=t, end=t + timedelta(minutes=30),
                          intensity=round(value), index=None))
    # Inject two anomalies (unusual spikes for their hour).
    slots[20] = Slot(slots[20].start, slots[20].end, 480, None)   # overnight spike
    slots[300] = Slot(slots[300].start, slots[300].end, 15, None) # midday collapse
    return slots


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "sample_output"
    out_dir.mkdir(exist_ok=True)
    log_path = out_dir / "intensity_log.csv"
    if log_path.exists():
        log_path.unlink()

    slots = synthetic_week()
    written = append_slots_to_log(slots, log_path)
    print(f"Logged {written} readings to {log_path.name}")

    df = load_log(log_path)
    print("Peak/off-peak:", peak_offpeak_summary(df))
    anomalies = detect_anomalies(df, z=2.5)
    print(f"Anomalies (|z|>=2.5): {len(anomalies)}")
    print(anomalies.to_string(index=False))

    xlsx = build_excel_report(
        df, out_dir / "grid_analysis.xlsx",
        metric_name="Carbon intensity", unit="gCO2/kWh", z=2.5,
    )
    print(f"Excel report written to {xlsx.name}")

    # --- forecasting: backtest the seasonal model, then forecast the next day ---
    from src.energyagent.analysis.forecast import backtest, forecast_next
    bt = backtest(df, test_hours=48)
    print("\nForecast backtest (48h hold-out):")
    print("  seasonal   :", bt["seasonal"])
    print("  persistence:", bt["persistence"])
    print(f"  seasonal beats persistence by {bt['mae_improvement_pct']}% MAE")

    fc = forecast_next(df, hours=24)
    print(f"\nNext-24h forecast: {len(fc)} half-hourly points, "
          f"first = {fc.iloc[0]['forecast']} gCO2/kWh at {fc.iloc[0]['start_utc']}")


if __name__ == "__main__":
    main()