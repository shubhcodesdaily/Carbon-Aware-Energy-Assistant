"""A genuine, honest forecasting baseline for the GB grid time-series.

Approach: a **seasonal profile** forecaster. Electricity carbon intensity and
price are dominated by daily and weekly cycles, so we learn the average level
for each half-hour-of-week from history and use that as the forecast. It's the
standard "seasonal naive / climatology" baseline a forecasting analyst starts
from — simple, explainable, and a real model with a real error metric.

We evaluate it honestly with a time-based backtest against a persistence
(last-value) baseline, reporting MAE / RMSE / sMAPE on held-out data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.energyagent.analysis.timeseries import UK_TZ


def _features(ts_utc: pd.Series) -> pd.DataFrame:
    """Local-time seasonal features: day-of-week and half-hour-of-day.

    Seasonality lives in UK local time (behaviour + daylight), so convert first.
    """
    local = ts_utc.dt.tz_convert(UK_TZ)
    dow = local.dt.dayofweek                      # 0=Mon .. 6=Sun
    half = local.dt.hour * 2 + (local.dt.minute >= 30).astype(int)  # 0..47
    return pd.DataFrame({
        "hhow": dow * 48 + half,   # half-hour-of-week: 0..335
        "hod": local.dt.hour,      # hour-of-day fallback: 0..23
    })


@dataclass
class SeasonalForecaster:
    """Learns an average level per half-hour-of-week, with graceful fallbacks."""
    by_hhow: dict[int, float] = field(default_factory=dict)
    by_hod: dict[int, float] = field(default_factory=dict)
    global_mean: float = 0.0

    def fit(self, df: pd.DataFrame) -> "SeasonalForecaster":
        feats = _features(df["start_utc"])
        work = df.assign(hhow=feats["hhow"].values, hod=feats["hod"].values)
        self.by_hhow = work.groupby("hhow")["value"].mean().to_dict()
        self.by_hod = work.groupby("hod")["value"].mean().to_dict()
        self.global_mean = float(work["value"].mean())
        return self

    def predict(self, timestamps: pd.Series) -> np.ndarray:
        feats = _features(pd.Series(pd.to_datetime(timestamps, utc=True)))
        out = []
        for hhow, hod in zip(feats["hhow"], feats["hod"]):
            if hhow in self.by_hhow:              # best: exact half-hour-of-week
                out.append(self.by_hhow[hhow])
            elif hod in self.by_hod:              # fallback: hour-of-day
                out.append(self.by_hod[hod])
            else:                                 # last resort: overall mean
                out.append(self.global_mean)
        return np.asarray(out, dtype=float)


# ---------- metrics ----------

def mae(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - pred)))


def rmse(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - pred) ** 2)))


def smape(actual: np.ndarray, pred: np.ndarray) -> float:
    """Symmetric MAPE (%) — robust to near-zero actuals, unlike plain MAPE."""
    denom = (np.abs(actual) + np.abs(pred))
    mask = denom != 0
    if not mask.any():
        return 0.0
    return float(np.mean(2 * np.abs(actual - pred)[mask] / denom[mask]) * 100)


# ---------- backtest ----------

def backtest(df: pd.DataFrame, test_hours: int = 48) -> dict:
    """Time-based hold-out: train on all but the last `test_hours`, forecast
    that held-out window, and score the seasonal model against a persistence
    (last-value) baseline.

    Returns a dict of metrics plus a frame of actual-vs-forecast for charting.
    """
    df = df.sort_values("start_utc").reset_index(drop=True)
    if df.empty:
        raise ValueError("No data to backtest.")

    cutoff = df["start_utc"].max() - pd.Timedelta(hours=test_hours)
    train = df[df["start_utc"] <= cutoff]
    test = df[df["start_utc"] > cutoff]
    if len(train) < 48 or test.empty:
        raise ValueError(
            f"Need >=1 day of training data and a non-empty test window; "
            f"got train={len(train)}, test={len(test)}."
        )

    model = SeasonalForecaster().fit(train)
    pred_seasonal = model.predict(test["start_utc"])

    # Persistence baseline: repeat the last observed training value.
    last_value = float(train["value"].iloc[-1])
    pred_persist = np.full(len(test), last_value)

    actual = test["value"].to_numpy(dtype=float)
    result = {
        "train_points": int(len(train)),
        "test_points": int(len(test)),
        "test_hours": test_hours,
        "seasonal": {
            "mae": round(mae(actual, pred_seasonal), 2),
            "rmse": round(rmse(actual, pred_seasonal), 2),
            "smape": round(smape(actual, pred_seasonal), 1),
        },
        "persistence": {
            "mae": round(mae(actual, pred_persist), 2),
            "rmse": round(rmse(actual, pred_persist), 2),
            "smape": round(smape(actual, pred_persist), 1),
        },
    }
    imp = result["persistence"]["mae"] - result["seasonal"]["mae"]
    base = result["persistence"]["mae"] or 1.0
    result["mae_improvement_pct"] = round(100 * imp / base, 1)

    forecast_frame = pd.DataFrame({
        "start_utc": test["start_utc"].values,
        "actual": actual,
        "forecast_seasonal": np.round(pred_seasonal, 1),
        "forecast_persistence": np.round(pred_persist, 1),
    })
    result["frame"] = forecast_frame
    return result


def forecast_next(df: pd.DataFrame, hours: int = 24, freq_min: int = 30) -> pd.DataFrame:
    """Fit on all history and forecast the next `hours` at half-hourly steps."""
    model = SeasonalForecaster().fit(df)
    start = df["start_utc"].max() + pd.Timedelta(minutes=freq_min)
    steps = int(hours * 60 / freq_min)
    future = pd.date_range(start=start, periods=steps, freq=f"{freq_min}min", tz="UTC")
    preds = model.predict(pd.Series(future))
    return pd.DataFrame({"start_utc": future, "forecast": np.round(preds, 1)})