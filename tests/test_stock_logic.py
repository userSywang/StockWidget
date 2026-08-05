import unittest

from StockLogic import (
    evaluate_price_alerts,
    evaluate_alert_rule,
    flatten_group_codes,
    normalize_code_or_none,
    normalize_alert_rule,
    normalize_price_alert,
    normalize_groups,
    normalize_strategy_alert_config,
    strategy_daily_request_codes,
    update_strategy_position_state,
    evaluate_strategy_alerts,
)


class StockLogicTests(unittest.TestCase):
    def test_normalize_code_supports_stock_etf_and_board_codes(self):
        self.assertEqual(normalize_code_or_none("600000"), "sh600000")
        self.assertEqual(normalize_code_or_none("512000"), "sh512000")
        self.assertEqual(normalize_code_or_none("000001"), "sz000001")
        self.assertEqual(normalize_code_or_none("865180"), "bk865180")
        self.assertEqual(normalize_code_or_none("bk865180"), "bk865180")

    def test_normalize_groups_migrates_legacy_codes(self):
        groups = normalize_groups([], ["sh000001", "512000", "512000"])

        self.assertEqual(groups, [{"name": "默认", "codes": ["sh000001", "sh512000"]}])
        self.assertEqual(flatten_group_codes(groups), ["sh000001", "sh512000"])

    def test_alert_rule_triggers_when_index_and_targets_match(self):
        rule = {
            "enabled": True,
            "index_code": "sh000001",
            "code_a": "sh512000",
            "pct_a": 2,
            "volume_a": True,
            "code_b": "sh515880",
            "pct_b": 3,
            "volume_b": False,
            "message": "触发",
        }
        previous = {
            "sh512000": {"volume": 100},
            "sh515880": {"volume": 200},
        }
        current = {
            "sh000001": {"change_pct": 0.2, "volume": 1},
            "sh512000": {"change_pct": 2.1, "volume": 150},
            "sh515880": {"change_pct": 3.2, "volume": 220},
        }

        self.assertTrue(evaluate_alert_rule(rule, current, previous)["triggered"])

    def test_alert_rule_respects_trigger_failure(self):
        rule = {
            "enabled": True,
            "index_code": "sh000001",
            "code_a": "sh512000",
            "pct_a": 2,
            "code_b": "sh515880",
            "pct_b": 3,
        }
        current = {
            "sh000001": {"change_pct": -0.1, "volume": 1},
            "sh512000": {"change_pct": 2.1, "volume": 150},
            "sh515880": {"change_pct": 3.2, "volume": 220},
        }

        self.assertFalse(evaluate_alert_rule(rule, current, {})["triggered"])

    def test_alert_rule_migrates_legacy_fields_to_dynamic_targets(self):
        rule = normalize_alert_rule({
            "enabled": True,
            "index_code": "sh000001",
            "code_a": "512000",
            "pct_a": 2,
            "volume_a": True,
            "code_b": "515880",
            "pct_b": 3,
        })

        self.assertEqual([target["code"] for target in rule["targets"]], ["sh000001", "sh512000", "sh515880"])
        self.assertEqual(rule["targets"][0]["op"], ">")
        self.assertEqual(rule["targets"][1]["pct"], 2.0)
        self.assertTrue(rule["targets"][1]["volume"])

    def test_alert_rule_supports_dynamic_targets(self):
        rule = {
            "enabled": True,
            "targets": [
                {"code": "sh000001", "op": ">", "pct": 0, "volume": False},
                {"code": "sh512000", "op": ">=", "pct": 2, "volume": True},
            ],
            "message": "触发",
        }
        previous = {"sh512000": {"volume": 100}}
        current = {
            "sh000001": {"change_pct": 0.1, "volume": 1},
            "sh512000": {"change_pct": 2.0, "volume": 120},
        }

        self.assertTrue(evaluate_alert_rule(rule, current, previous)["triggered"])

    def test_price_alert_triggers_above_and_below_thresholds(self):
        alerts = [
            {"enabled": True, "code": "512000", "direction": "above", "price": 1.2, "message": "突破"},
            {"enabled": True, "code": "515880", "direction": "below", "price": 0.9, "message": "跌破"},
        ]
        quotes = {
            "sh512000": {"name": "ETF A", "price": 1.21},
            "sh515880": {"name": "ETF B", "price": 0.89},
        }

        result = evaluate_price_alerts(alerts, quotes)

        self.assertIn("sh512000", result)
        self.assertIn("sh515880", result)
        self.assertIn("突破", result["sh512000"][0]["detail"])
        self.assertTrue(result["sh512000"][0]["triggered"])

    def test_price_alert_returns_untriggered_enabled_alerts(self):
        alerts = [
            {"enabled": True, "code": "512000", "direction": "above", "price": 2.0, "message": "突破"},
        ]
        quotes = {
            "sh512000": {"name": "ETF A", "price": 1.21},
        }

        result = evaluate_price_alerts(alerts, quotes)

        self.assertIn("sh512000", result)
        self.assertFalse(result["sh512000"][0]["triggered"])
        self.assertIn("未触发", result["sh512000"][0]["detail"])

    def test_price_alert_normalizes_invalid_values(self):
        alert = normalize_price_alert({"code": "512000", "direction": "bad", "price": "bad"})

        self.assertEqual(alert["code"], "sh512000")
        self.assertEqual(alert["direction"], "above")
        self.assertEqual(alert["price"], 0.0)

    def test_strategy_alert_config_normalizes_positions_and_rules(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [
                {"code": "512000", "cost_price": "1.234", "position_pct": 120, "buy_date": "2026-08-05"},
                {"code": "bad"},
            ],
            "notifications": {
                "desktop_popup": False,
                "panel_highlight": True,
                "remote_push": True,
                "remote_channel": "custom",
                "webhook_url": " https://example.test/webhook ",
            },
            "rules": {"max_loss_pct": "6", "stale_position_days": "10"},
        })

        self.assertTrue(config["enabled"])
        self.assertEqual(config["positions"][0]["code"], "sh512000")
        self.assertEqual(config["positions"][0]["cost_price"], 1.234)
        self.assertEqual(config["positions"][0]["position_pct"], 100.0)
        self.assertFalse(config["notifications"]["desktop_popup"])
        self.assertTrue(config["notifications"]["panel_highlight"])
        self.assertTrue(config["notifications"]["remote_push"])
        self.assertEqual(config["notifications"]["remote_channel"], "custom")
        self.assertEqual(config["notifications"]["webhook_url"], "https://example.test/webhook")
        self.assertEqual(config["rules"]["max_loss_pct"], 6.0)
        self.assertEqual(config["rules"]["stale_position_days"], 10)

    def test_strategy_trailing_profit_locks_to_lower_profit_line(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0, "position_pct": 20.0}],
        })

        updated, changed = update_strategy_position_state(config, {"sh603259": {"price": 120.0, "name": "药明康德"}})
        states = evaluate_strategy_alerts(updated, {"sh603259": {"price": 109.0, "name": "药明康德"}})

        self.assertTrue(changed)
        self.assertEqual(updated["positions"][0]["peak_profit_pct"], 20.0)
        self.assertEqual(updated["positions"][0]["locked_profit_pct"], 10.0)
        self.assertTrue(states[0]["triggered"])
        self.assertIn("触发锁盈10%", states[0]["status"])

    def test_strategy_daily_request_codes_include_market_indexes(self):
        codes = strategy_daily_request_codes({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
            "rules": {"index_ma5_break_enabled": True, "index_ma10_break_enabled": True},
        })

        self.assertEqual(codes, ["sh603259", "sh000001", "sz399001"])

    def test_strategy_alerts_trigger_on_stock_and_index_ma_breaks(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
            "rules": {
                "stock_ma5_break_enabled": True,
                "index_ma5_break_enabled": True,
                "index_ma10_break_enabled": True,
            },
        })
        daily_by_code = {
            "sh603259": [{"close": v} for v in [100, 101, 102, 103, 104]],
            "sh000001": [{"close": v} for v in [3000, 3010, 3020, 3030, 3040, 3050, 3060, 3070, 3080, 3090]],
            "sz399001": [{"close": v} for v in [9000, 9010, 9020, 9030, 9040, 9050, 9060, 9070, 9080, 9090]],
        }
        quotes = {
            "sh603259": {"price": 99.0, "name": "药明康德"},
            "sh000001": {"price": 3000.0},
            "sz399001": {"price": 8800.0},
        }

        states = evaluate_strategy_alerts(config, quotes, daily_by_code)

        self.assertTrue(states[0]["triggered"])
        self.assertIn("个股破5日线", states[0]["status"])
        self.assertIn("上证破5日线", states[0]["status"])
        self.assertIn("深成破10日线", states[0]["status"])


if __name__ == "__main__":
    unittest.main()
