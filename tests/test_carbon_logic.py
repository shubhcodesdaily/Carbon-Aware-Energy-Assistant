"""Tests for the carbon logic. Run with:  python tests/test_carbon_logic.py"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the project importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.energyagent.tools.carbon_logic import (
    Slot,
    find_greenest_window,
    parse_forecast,
    slots_for_duration,
)


def _slot(hour, minute, intensity):
    """Small helper to build a Slot quickly."""
    start = datetime(2026, 1, 15, hour, minute, tzinfo=timezone.utc)
    end = start
    return Slot(start=start, end=end, intensity=intensity, index="x")


def test_parse_prefers_actual_over_forecast():
    payload = {"data": [
        {"from": "2026-01-15T12:00Z", "to": "2026-01-15T12:30Z",
         "intensity": {"forecast": 266, "actual": 263, "index": "moderate"}},
    ]}
    slots = parse_forecast(payload)
    assert len(slots) == 1
    assert slots[0].intensity == 263      # actual wins over forecast


def test_slots_for_duration_rounds_up():
    assert slots_for_duration(1) == 2     # 1 hour = 2 slots
    assert slots_for_duration(2) == 4     # 2 hours = 4 slots
    assert slots_for_duration(1.25) == 3  # 2.5 slots rounds up to 3


def test_finds_lowest_average_block():
    # A dip in the middle: slots at 13:00 and 13:30 are the cleanest pair.
    slots = [
        _slot(12, 0, 200), _slot(12, 30, 180),
        _slot(13, 0, 40),  _slot(13, 30, 30),
        _slot(14, 0, 150), _slot(14, 30, 160),
    ]
    window = find_greenest_window(slots, hours=1)  # needs 2 slots
    assert window.avg_intensity == 35    # (40 + 30) / 2
    assert window.start.hour == 13 and window.start.minute == 0


def test_skips_windows_with_missing_data():
    # Every low pair straddles a None, so only the (50, 60) pair is scoreable.
    slots = [
        _slot(0, 0, 10),  _slot(0, 30, None),
        _slot(1, 0, 12),  _slot(1, 30, None),
        _slot(2, 0, 50),  _slot(2, 30, 60),
    ]
    window = find_greenest_window(slots, hours=1)
    assert window.avg_intensity == 55    # (50 + 60) / 2


if __name__ == "__main__":
    # A tiny runner, so this file works even without pytest installed.
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")