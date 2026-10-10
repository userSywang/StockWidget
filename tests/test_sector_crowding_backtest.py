# -*- coding: utf-8 -*-
import unittest

import numpy as np
import pandas as pd

from tools.backtest_sector_crowding import (
    acceptance,
    add_trend_features,
    rolling_percentile,
    select_confirmed_signal_indices,
    select_signal_indices,
)


class SectorCrowdingBacktestTests(unittest.TestCase):
    def test_rolling_percentile_uses_current_and_past_values_only(self):
        values = pd.Series(np.arange(1.0, 261.0))
        result = rolling_percentile(values, window=252, minimum=252)

        self.assertTrue(result.iloc[:251].isna().all())
        self.assertEqual(result.iloc[251], 100.0)
        self.assertEqual(result.iloc[252], 100.0)

    def test_signal_selection_uses_crossing_and_cooldown(self):
        frame = pd.DataFrame({"crowding": [20, 9, 8, 12, 9, 11] + [20] * 17 + [9]})

        self.assertEqual(select_signal_indices(frame, cooldown=20), [1, 23])

    def test_five_day_rebound_requires_five_consecutive_increases(self):
        frame = pd.DataFrame({
            "crowding": [20, 9, 8, 9, 8, 9, 10, 11, 12, 13],
            "close": [100] * 10,
        })

        signals = select_confirmed_signal_indices(frame, "crowding_rise_5", max_wait=20)

        self.assertEqual(signals, [9])

    def test_three_day_rebound_requires_three_consecutive_increases(self):
        frame = pd.DataFrame({
            "crowding": [20, 9, 8, 9, 8, 9, 10, 11],
            "close": [100] * 8,
        })

        signals = select_confirmed_signal_indices(frame, "crowding_rise_3", max_wait=20)

        self.assertEqual(signals, [7])

    def test_daily_weekly_confirmation_uses_completed_week_only(self):
        dates = pd.bdate_range("2024-01-01", periods=70)
        close = pd.Series(np.linspace(100.0, 80.0, 55).tolist() + np.linspace(82.0, 110.0, 15).tolist())
        frame = pd.DataFrame({
            "date": dates,
            "close": close,
            "crowding": [20.0] * 45 + [9.0] + [8.0] * 24,
        })
        featured = add_trend_features(frame)

        signals = select_confirmed_signal_indices(featured, "daily_weekly", max_wait=24)

        self.assertLessEqual(len(signals), 1)
        if signals:
            index = signals[0]
            self.assertGreater(featured.at[index, "close"], featured.at[index, "ma20"])
            self.assertTrue(bool(featured.at[index, "weekly_uptrend"]))

    def test_market_filter_aligns_benchmark_by_date_without_lookahead(self):
        dates = pd.bdate_range("2024-01-01", periods=70)
        frame = pd.DataFrame({
            "date": dates,
            "close": np.linspace(100.0, 120.0, 70),
            "crowding": [20.0] * 45 + [9.0] + [8.0] * 24,
        })
        benchmark = pd.DataFrame({
            "date": dates,
            "close": np.linspace(120.0, 80.0, 70),
        })
        featured = add_trend_features(frame, benchmark)

        signals = select_confirmed_signal_indices(featured, "daily_weekly_market", max_wait=24)

        self.assertEqual(signals, [])

    def test_ma20_volume_confirmation_requires_above_average_volume(self):
        frame = pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=30),
            "close": [100.0] * 20 + [90.0, 91.0, 92.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "volume": [100.0] * 24 + [90.0] * 5 + [200.0],
            "crowding": [20.0] * 19 + [9.0] + [8.0] * 10,
        })
        featured = add_trend_features(frame)

        signals = select_confirmed_signal_indices(featured, "ma20_volume", max_wait=10)

        self.assertEqual(signals, [29])

    def test_confirmation_does_not_count_same_entry_for_multiple_ice_events(self):
        frame = pd.DataFrame({
            "crowding": [20.0, 9.0, 11.0] + [20.0] * 20 + [9.0] + [8.0] * 16,
            "close": [90.0] * 30 + [110.0] * 10,
            "ma20": [100.0] * 40,
        })

        signals = select_confirmed_signal_indices(frame, "ma20_reclaim", max_wait=40)

        self.assertEqual(signals, [30])

    def test_acceptance_rejects_small_samples(self):
        result = {
            "120": {"samples": 29, "positive_rate_pct": 100.0, "median_excess_return_pct": 10.0},
            "250": {"samples": 29, "positive_rate_pct": 100.0, "median_excess_return_pct": 10.0},
        }

        self.assertEqual(acceptance(result), "暂未验收（样本不足）")

    def test_acceptance_handles_no_evaluable_samples(self):
        result = {
            "120": {"samples": 0, "positive_rate_pct": None, "median_excess_return_pct": None},
            "250": {"samples": 0, "positive_rate_pct": None, "median_excess_return_pct": None},
        }

        self.assertEqual(acceptance(result), "无可评估样本")

    def test_acceptance_requires_both_long_horizons(self):
        result = {
            "120": {"samples": 30, "positive_rate_pct": 70.0, "median_excess_return_pct": 2.0},
            "250": {"samples": 30, "positive_rate_pct": 60.0, "median_excess_return_pct": 2.0},
        }

        self.assertEqual(acceptance(result), "未达到")

    def test_acceptance_reports_failed_metrics_and_small_sample(self):
        result = {
            "120": {"samples": 7, "positive_rate_pct": 40.0, "median_excess_return_pct": -1.0},
            "250": {"samples": 7, "positive_rate_pct": 70.0, "median_excess_return_pct": 2.0},
        }

        self.assertEqual(acceptance(result), "未达到（样本亦不足）")


if __name__ == "__main__":
    unittest.main()
