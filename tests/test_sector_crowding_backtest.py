# -*- coding: utf-8 -*-
import unittest

import numpy as np
import pandas as pd

from tools.backtest_sector_crowding import acceptance, rolling_percentile, select_signal_indices


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

    def test_acceptance_rejects_small_samples(self):
        result = {
            "120": {"samples": 29, "positive_rate_pct": 100.0, "median_excess_return_pct": 10.0},
            "250": {"samples": 29, "positive_rate_pct": 100.0, "median_excess_return_pct": 10.0},
        }

        self.assertEqual(acceptance(result), "暂未验收（样本不足）")

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
