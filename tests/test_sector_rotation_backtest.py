# -*- coding: utf-8 -*-
import unittest

import numpy as np
import pandas as pd

from tools.backtest_sector_rotation import (
    add_rotation_features,
    evaluate_short_term,
    select_rotation_signals,
)


class SectorRotationBacktestTests(unittest.TestCase):
    def test_recent_low_uses_current_and_past_crowding_only(self):
        frame = pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=12),
            "close": np.arange(100.0, 112.0),
            "volume": [100.0] * 12,
            "crowding": [30.0] * 5 + [15.0] + [30.0] * 6,
        })
        benchmark = frame[["date", "close"]].copy()

        result = add_rotation_features(frame, benchmark)

        self.assertFalse(bool(result.at[4, "recent_low"]))
        self.assertTrue(bool(result.at[5, "recent_low"]))
        self.assertTrue(bool(result.at[11, "recent_low"]))

    def test_relative_strength_confirmation_selects_once_per_low_event(self):
        frame = pd.DataFrame({
            "crowding": [30.0, 15.0] + [25.0] * 12,
            "recent_low": [False, True] + [True] * 9 + [False] * 3,
            "close": [100.0] * 2 + [101.0] * 12,
            "ma5": [100.0] * 14,
            "relative_strength_3": [0.0] * 4 + [0.03] * 10,
            "previous_high_5": [110.0] * 14,
            "volume_ratio_20": [1.0] * 14,
            "daily_return": [0.0] * 14,
            "benchmark_daily_return": [0.0] * 14,
        })

        signals = select_rotation_signals(frame, "relative_strength_3", max_wait=10)

        self.assertEqual(signals, [4])

    def test_short_term_evaluation_does_not_include_signal_day(self):
        dates = pd.bdate_range("2024-01-01", periods=6)
        frame = pd.DataFrame({
            "date": dates,
            "close": [100.0, 101.0, 104.0, 99.0, 106.0, 105.0],
        })
        benchmark = pd.DataFrame({"date": dates, "close": [100.0] * 6})

        result = evaluate_short_term(frame, benchmark, [0], horizons=(3,))

        self.assertEqual(result["3"]["samples"], 1)
        self.assertAlmostEqual(result["3"]["median_max_gain_pct"], 4.0)
        self.assertAlmostEqual(result["3"]["median_max_adverse_pct"], -1.0)

    def test_market_baseline_samples_valid_history_at_fixed_intervals(self):
        frame = pd.DataFrame({
            "crowding": [np.nan, np.nan] + [30.0] * 10,
        })

        signals = select_rotation_signals(frame, "market_baseline", cooldown=3)

        self.assertEqual(signals, [2, 5, 8, 11])


if __name__ == "__main__":
    unittest.main()
