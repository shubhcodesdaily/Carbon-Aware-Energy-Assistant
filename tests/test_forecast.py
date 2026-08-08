"""Tests for the seasonal forecaster and backtest.
Run with:  python tests/test_forecast.py
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.energyagent.analysis.forecast import (
    SeasonalForecaster, backtest, forecast_next, mae, smape,
)


def _synthetic(days: int = 21) -> pd.DataFrame:
    """Half-hourly series with a daily curve + weekend effect + small noise."""
    rng = np.random.default_rng(0)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # a Monday
    rows = []
    for i in range(48 * days):
        t = start + timedelta(minutes=30 * i)
        hour = t.hour + t.minute / 60
        daily = 160 + 90 * math.sin((hour - 10) / 24 * 2 * math.pi)
        weekend = -30 if t.weekday() >= 5 else 0          # cleaner at weekends
        value = max(20, daily + weekend + rng.normal(0, 8))
        rows.append({"start_utc": pd.Timestamp(t), "value": value})
    return pd.DataFrame(rows)


def test_seasonal_beats_persistence_on_horizon():
    df = _synthetic(21)
    result = backtest(df, test_hours=48)
    # Over a 48h horizon, a seasonal profile should clearly beat last-value.
    assert result["seasonal"]["mae"] < result["persistence"]["mae"]
    assert result["mae_improvement_pct"] > 20


def test_forecaster_learns_daily_shape():
    df = _synthetic(14)
    model = SeasonalForecaster().fit(df)
    # 04:00 (overnight trough) should forecast lower than 18:00 (evening peak).
    trough = model.predict(pd.Series([pd.Timestamp("2026-02-02T04:00Z")]))[0]
    peak = model.predict(pd.Series([pd.Timestamp("2026-02-02T18:00Z")]))[0]
    assert trough < peak


def test_forecast_next_shape():
    df = _synthetic(10)
    fc = forecast_next(df, hours=24)
    assert len(fc) == 48                       # 24h at half-hourly = 48 steps
    assert fc["start_utc"].min() > df["start_utc"].max()


def test_metrics_sane():
    a = np.array([100.0, 100.0, 100.0])
    assert mae(a, a) == 0.0
    assert smape(a, a) == 0.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")