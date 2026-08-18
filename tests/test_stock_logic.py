import unittest
from datetime import date

from StockLogic import (
    evaluate_price_alerts,
    evaluate_alert_rule,
    flatten_group_codes,
    normalize_code_or_none,
    normalize_alert_rule,
    normalize_alert_rules,
    normalize_price_alert,
    price_alert_is_expired,
    normalize_groups,
    normalize_strategy_alert_config,
    quote_has_trade,
    strategy_action_rules_for_position,
    strategy_action_rules_from_rules,
    strategy_daily_request_codes,
    update_strategy_position_state,
    evaluate_strategy_actions,
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

    def test_alert_rules_drop_legacy_tech_resonance_rule(self):
        rules = normalize_alert_rules([
            {
                "enabled": True,
                "name": "科技共振",
                "display_mode": "always",
                "targets": [{"code": "sh000001", "op": ">", "pct": 0.0}],
            }
        ])

        self.assertEqual(rules, [])

    def test_default_alert_rule_uses_generic_name(self):
        rules = normalize_alert_rules([])

        self.assertEqual(rules[0]["name"], "联动提醒")
        self.assertNotIn("科技共振", rules[0]["message"])

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
        self.assertEqual(alert["expire_days"], 30)

    def test_price_alert_expiration_uses_created_date_and_valid_days(self):
        alert = normalize_price_alert({
            "code": "512000",
            "created_date": "2026-08-01",
            "expire_days": 5,
        })

        self.assertFalse(price_alert_is_expired(alert, date(2026, 8, 5)))
        self.assertTrue(price_alert_is_expired(alert, date(2026, 8, 6)))

    def test_price_alert_triggers_when_below_ma5(self):
        alerts = [{"enabled": True, "code": "603259", "direction": "below_ma5", "message": "低吸观察"}]
        quotes = {"sh603259": {"price": 9.0, "name": "药明康德"}}
        daily_by_code = {"sh603259": [{"close": value} for value in [10, 10, 10, 10, 10]]}

        result = evaluate_price_alerts(alerts, quotes, daily_by_code)

        self.assertTrue(result["sh603259"][0]["triggered"])
        self.assertEqual(result["sh603259"][0]["direction"], "below_ma5")
        self.assertEqual(result["sh603259"][0]["price"], 10.0)

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
                "daily_summary_time": "14:30",
            },
            "rules": {"max_loss_pct": "6", "stale_position_days": "10"},
        })

        self.assertTrue(config["enabled"])
        self.assertEqual(config["positions"][0]["code"], "sh512000")
        self.assertEqual(config["positions"][0]["cost_price"], 1.234)
        self.assertNotIn("position_pct", config["positions"][0])
        self.assertFalse(config["notifications"]["desktop_popup"])
        self.assertTrue(config["notifications"]["panel_highlight"])
        self.assertTrue(config["notifications"]["remote_push"])
        self.assertEqual(config["notifications"]["remote_channel"], "custom")
        self.assertEqual(config["notifications"]["webhook_url"], "https://example.test/webhook")
        self.assertEqual(config["notifications"]["daily_summary_time"], "14:30")
        self.assertEqual(config["notifications"]["push_cooldown_minutes"], 30)
        self.assertEqual(config["rules"]["max_loss_pct"], 6.0)
        self.assertEqual(config["rules"]["stale_position_days"], 10)
        self.assertEqual(config["rule_schema_version"], 1)
        self.assertTrue(any(rule["id"] == "max_loss" for rule in config["action_rules"]))

    def test_strategy_alert_config_includes_turtle_template(self):
        config = normalize_strategy_alert_config({})

        profiles = {profile["id"]: profile for profile in config["strategy_profiles"]}

        self.assertIn("turtle:classic", profiles)
        self.assertEqual(profiles["turtle:classic"]["strategy_type"], "turtle")
        self.assertEqual(profiles["turtle:classic"]["turtle_params"]["position_sizing"], "atr_risk")
        turtle_rules = {rule["id"]: rule for rule in profiles["turtle:classic"]["action_rules"]}
        self.assertEqual(turtle_rules["turtle_entry_20d"]["condition"]["threshold"]["period"], 20)
        self.assertEqual(turtle_rules["turtle_atr_stop"]["condition"]["threshold"]["multiple"], 2.0)
        self.assertEqual(turtle_rules["turtle_pyramid_0_5atr"]["condition"]["threshold"]["multiple"], 0.5)
        self.assertEqual(turtle_rules["turtle_exit_10d"]["condition"]["threshold"]["period"], 10)

    def test_turtle_template_params_drive_action_rules(self):
        config = normalize_strategy_alert_config({
            "strategy_profiles": [{
                "id": "turtle:custom",
                "name": "自定义海龟",
                "strategy_type": "turtle",
                "turtle_params": {
                    "entry_days": 55,
                    "exit_days": 20,
                    "atr_stop_multiple": 3.0,
                    "pyramid_atr_multiple": 1.0,
                    "max_units": 3,
                    "position_sizing": "fixed_percent",
                },
            }],
        })

        profile = next(item for item in config["strategy_profiles"] if item["id"] == "turtle:custom")
        rules = {rule["id"]: rule for rule in profile["action_rules"]}

        self.assertEqual(profile["turtle_params"]["position_sizing"], "fixed_percent")
        self.assertEqual(rules["turtle_entry_20d"]["condition"]["threshold"]["period"], 55)
        self.assertEqual(rules["turtle_exit_10d"]["condition"]["threshold"]["period"], 20)
        self.assertEqual(rules["turtle_atr_stop"]["condition"]["threshold"]["multiple"], 3.0)
        self.assertEqual(rules["turtle_pyramid_0_5atr"]["action"]["max_units"], 3)

    def test_turtle_template_preserves_structured_action_rule_parameters(self):
        config = normalize_strategy_alert_config({
            "strategy_profiles": [{
                "id": "turtle:custom",
                "name": "自定义海龟",
                "strategy_type": "turtle",
                "turtle_params": {"entry_days": 20},
                "action_rules": [{
                    "id": "turtle_entry_20d",
                    "name": "突破提醒",
                    "enabled": True,
                    "condition": {
                        "metric": "stock_price",
                        "operator": ">",
                        "threshold": {"type": "donchian_high", "period": 20},
                    },
                    "parameter": {"value": 55, "unit": "day_high"},
                    "action": {"type": "entry_signal"},
                }],
            }],
        })

        profile = next(item for item in config["strategy_profiles"] if item["id"] == "turtle:custom")
        rule = profile["action_rules"][0]

        self.assertEqual(rule["parameter"], {"value": 55, "unit": "day_high"})
        self.assertEqual(rule["condition"]["threshold"]["period"], 55)

    def test_strategy_alert_config_normalizes_push_cooldown(self):
        config = normalize_strategy_alert_config({
            "notifications": {"push_cooldown_minutes": "5"},
        })

        self.assertEqual(config["notifications"]["push_cooldown_minutes"], 5)

    def test_strategy_alert_config_defaults_daily_summary_to_trading_day_times(self):
        config = normalize_strategy_alert_config({
            "notifications": {"daily_summary_time": "bad"},
        })

        self.assertEqual(config["notifications"]["daily_summary_time"], "09:00,18:00")

    def test_strategy_config_does_not_drop_unknown_position_records(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "legacy-code", "cost_price": 10.0}],
        })

        self.assertEqual(len(config["positions"]), 1)
        self.assertEqual(config["positions"][0]["code"], "legacy-code")

    def test_strategy_action_rules_convert_legacy_rules(self):
        rules = strategy_action_rules_from_rules({
            "max_loss_enabled": True,
            "max_loss_pct": 7.5,
            "stock_ma5_break_enabled": True,
            "index_ma5_break_enabled": False,
            "trailing_profit_enabled": True,
            "trailing_tiers": [
                {"profit_pct": 20, "lock_pct": 10},
                {"profit_pct": 40, "lock_pct": 30},
            ],
            "reduce_half_enabled": True,
            "reduce_half_profit_pct": 45,
            "stale_position_enabled": True,
            "stale_position_days": 12,
        })

        by_id = {rule["id"]: rule for rule in rules}
        self.assertEqual(by_id["max_loss"]["condition"]["threshold"]["value"], -7.5)
        self.assertEqual(by_id["stock_ma5_break"]["condition"]["threshold"]["period"], 5)
        self.assertFalse(by_id["index_ma5_break"]["enabled"])
        self.assertEqual(by_id["trailing_profit"]["condition"]["threshold"]["tiers"][1]["lock_pct"], 30.0)
        self.assertEqual(by_id["reduce_half"]["action"]["type"], "reduce_position")
        self.assertNotIn("position_cap", by_id)
        self.assertNotIn("block_heavy_on_index_ma5_down", by_id)
        self.assertEqual(by_id["stale_position"]["condition"]["threshold"]["value"], 12)

    def test_strategy_action_rules_for_position_use_resolved_position_rules(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "rules": {"max_loss_enabled": True, "max_loss_pct": 5.0},
            "positions": [
                {
                    "code": "603259",
                    "cost_price": 100.0,
                    "rules": {"max_loss_enabled": True, "max_loss_pct": 10.0},
                },
                {
                    "code": "600584",
                    "cost_price": 100.0,
                    "rules": {"max_loss_enabled": True, "max_loss_pct": 5.0},
                },
            ],
        })

        first_rules = {rule["id"]: rule for rule in strategy_action_rules_for_position(config, config["positions"][0])}
        second_rules = {rule["id"]: rule for rule in strategy_action_rules_for_position(config, config["positions"][1])}

        self.assertEqual(first_rules["max_loss"]["condition"]["threshold"]["value"], -10.0)
        self.assertEqual(second_rules["max_loss"]["condition"]["threshold"]["value"], -5.0)

    def test_strategy_action_rules_for_position_use_turtle_profile_actions(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0, "strategy_id": "turtle:classic"}],
        })

        rules = {rule["id"]: rule for rule in strategy_action_rules_for_position(config, config["positions"][0])}

        self.assertIn("turtle_entry_20d", rules)
        self.assertIn("turtle_atr_stop", rules)
        self.assertNotIn("max_loss", rules)

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

    def test_strategy_position_rules_override_global_rules(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "rules": {"max_loss_enabled": True, "max_loss_pct": 5.0},
            "positions": [{
                "code": "603259",
                "cost_price": 100.0,
                "rules": {"max_loss_enabled": True, "max_loss_pct": 10.0},
            }],
        })

        states = evaluate_strategy_alerts(config, {"sh603259": {"price": 94.0}})

        self.assertFalse(states[0]["triggered"])
        self.assertEqual(config["positions"][0]["rules"]["max_loss_pct"], 10.0)

    def test_strategy_profiles_bind_different_rules_to_different_positions(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "rules": {"max_loss_enabled": True, "max_loss_pct": 5.0},
            "strategy_profiles": [
                {"id": "steady", "name": "稳健", "rules": {"max_loss_pct": 10.0}},
                {"id": "tight", "name": "严格", "rules": {"max_loss_pct": 2.0}},
            ],
            "positions": [
                {"code": "603259", "cost_price": 100.0, "strategy_id": "steady"},
                {"code": "512000", "cost_price": 100.0, "strategy_id": "tight"},
            ],
        })

        states = evaluate_strategy_alerts(config, {
            "sh603259": {"price": 94.0},
            "sh512000": {"price": 94.0},
        })

        self.assertFalse(states[0]["triggered"])
        self.assertTrue(states[1]["triggered"])

    def test_strategy_daily_request_codes_include_shanghai_index_only(self):
        codes = strategy_daily_request_codes({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
            "rules": {"index_ma5_break_enabled": True, "index_ma10_break_enabled": True},
        })

        self.assertEqual(codes, ["sh603259", "sh000001"])

    def test_strategy_action_engine_reports_triggered_actions(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "rules": {
                "max_loss_enabled": True,
                "max_loss_pct": 5.0,
                "reduce_half_enabled": True,
                "reduce_half_profit_pct": 45.0,
            },
            "positions": [{"code": "603259", "cost_price": 100.0, "position_pct": 20.0}],
        })

        loss_actions = evaluate_strategy_actions(
            config,
            config["positions"][0],
            {"price": 94.0, "name": "药明康德"},
            {},
            {},
        )
        profit_actions = evaluate_strategy_actions(
            config,
            config["positions"][0],
            {"price": 146.0, "name": "药明康德"},
            {},
            {},
        )

        self.assertEqual(loss_actions[0]["rule_id"], "max_loss")
        self.assertEqual(loss_actions[0]["action_type"], "clear_position")
        self.assertEqual(loss_actions[0]["severity"], "danger")
        self.assertEqual(profit_actions[0]["rule_id"], "reduce_half")
        self.assertEqual(profit_actions[0]["action_type"], "reduce_position")
        self.assertEqual(profit_actions[0]["severity"], "warning")

    def test_strategy_alert_states_include_triggered_actions(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "rules": {"max_loss_enabled": True, "max_loss_pct": 5.0},
            "positions": [{"code": "603259", "cost_price": 100.0, "position_pct": 20.0}],
        })

        states = evaluate_strategy_alerts(config, {"sh603259": {"price": 94.0, "name": "药明康德"}})

        self.assertTrue(states[0]["triggered"])
        self.assertEqual(states[0]["triggered_actions"][0]["rule_id"], "max_loss")
        self.assertEqual(states[0]["triggered_actions"][0]["stock_name"], "药明康德")

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
        self.assertNotIn("深成", states[0]["status"])

    def test_strategy_alerts_include_display_indicators_and_stop_price(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0, "locked_profit_pct": 10.0}],
            "rules": {
                "max_loss_enabled": True,
                "max_loss_pct": 5.0,
                "stock_ma5_break_enabled": True,
                "index_ma5_break_enabled": True,
                "index_ma10_break_enabled": False,
                "trailing_profit_enabled": True,
                "reduce_half_enabled": False,
                "block_heavy_position_on_index_ma5_down": False,
                "stale_position_enabled": False,
            },
        })
        daily_rows = [{"close": float(v)} for v in range(1, 21)]

        states = evaluate_strategy_alerts(
            config,
            {"sh603259": {"price": 112.0, "name": "药明康德"}},
            {"sh603259": daily_rows},
        )

        self.assertEqual(states[0]["stop_price"], 110.0)
        self.assertEqual(states[0]["stop_loss_price"], 95.0)
        self.assertEqual(states[0]["take_profit_price"], 110.0)
        self.assertEqual(states[0]["ma5"], 18.0)
        self.assertEqual(states[0]["ma10"], 15.5)
        self.assertEqual(states[0]["ma20"], 10.5)
        self.assertEqual(states[0]["enabled_rules"], ["止损", "个股MA5", "大盘MA5", "移动止盈"])

    def test_strategy_stop_line_uses_stock_ma5_when_ma_clearance_enabled(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0, "locked_profit_pct": 0.0}],
            "rules": {
                "max_loss_enabled": True,
                "max_loss_pct": 10.0,
                "stock_ma5_break_enabled": True,
                "index_ma5_break_enabled": False,
                "index_ma10_break_enabled": False,
                "trailing_profit_enabled": False,
                "reduce_half_enabled": False,
                "stale_position_enabled": False,
            },
        })
        daily_rows = [{"close": value} for value in [100.0, 101.0, 102.0, 103.0, 104.0]]

        states = evaluate_strategy_alerts(
            config,
            {"sh603259": {"price": 103.0, "name": "药明康德"}},
            {"sh603259": daily_rows},
        )

        self.assertEqual(states[0]["ma5"], 102.0)
        self.assertEqual(states[0]["stop_loss_price"], 102.0)
        self.assertEqual(states[0]["stop_price"], 102.0)

    def test_strategy_alert_reports_raised_stop_line_and_price(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
        })
        updated, changed = update_strategy_position_state(config, {"sh603259": {"price": 120.0}})
        states = evaluate_strategy_alerts(updated, {"sh603259": {"price": 115.0}})

        self.assertTrue(changed)
        self.assertTrue(states[0]["lock_raised"])
        self.assertTrue(states[0]["triggered"])
        self.assertEqual(states[0]["severity"], "warning")
        self.assertEqual(states[0]["stop_price"], 110.0)
        self.assertIn("上调止盈线至110.00", states[0]["status"])

    def test_strategy_alert_initializes_stop_line_without_alert(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0, "locked_profit_pct": 10.0}],
        })
        updated, changed = update_strategy_position_state(config, {"sh603259": {"price": 115.0}})
        states = evaluate_strategy_alerts(updated, {"sh603259": {"price": 115.0}})

        self.assertTrue(changed)
        self.assertEqual(updated["positions"][0]["last_stop_price"], 110.0)
        self.assertFalse(updated["positions"][0]["stop_line_changed"])
        self.assertFalse(states[0]["triggered"])
        self.assertIn("已锁盈10%", states[0]["status"])

    def test_strategy_alert_triggers_when_existing_stop_line_changes_without_lock_raise(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{
                "code": "603259",
                "cost_price": 100.0,
                "locked_profit_pct": 10.0,
                "last_stop_price": 109.0,
            }],
        })
        updated, changed = update_strategy_position_state(config, {"sh603259": {"price": 115.0}})
        states = evaluate_strategy_alerts(updated, {"sh603259": {"price": 115.0}})

        self.assertTrue(changed)
        self.assertFalse(states[0]["lock_raised"])
        self.assertTrue(states[0]["stop_line_changed"])
        self.assertTrue(states[0]["triggered"])
        self.assertEqual(states[0]["severity"], "warning")
        self.assertEqual(states[0]["stop_line_previous_price"], 109.0)
        self.assertEqual(states[0]["stop_price"], 110.0)
        self.assertIn("止盈线变动至110.00", states[0]["status"])

    def test_stock_and_index_ma5_conditions_report_clearance(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
            "rules": {
                "stock_ma5_break_enabled": True,
                "index_ma5_break_enabled": True,
                "index_ma10_break_enabled": False,
            },
        })
        daily = {
            "sh603259": [{"close": value} for value in [100, 101, 102, 103, 104]],
            "sh000001": [{"close": value} for value in [3000, 3010, 3020, 3030, 3040]],
            "sz399001": [{"close": value} for value in [9000, 9010, 9020, 9030, 9040]],
        }
        states = evaluate_strategy_alerts(config, {
            "sh603259": {"price": 99.0},
            "sh000001": {"price": 3000.0},
            "sz399001": {"price": 8800.0},
        }, daily)

        self.assertTrue(states[0]["triggered"])
        self.assertIn("个股破5日线清仓", states[0]["status"])
        self.assertIn("大盘", states[0]["status"])
        self.assertIn("清仓", states[0]["status"])

    def test_strategy_alerts_report_daily_source_unavailable(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
            "rules": {
                "stock_ma5_break_enabled": True,
                "index_ma5_break_enabled": True,
            },
        })
        quotes = {
            "sh603259": {"price": 101.0, "name": "药明康德"},
            "sh000001": {"price": 3000.0},
        }

        states = evaluate_strategy_alerts(config, quotes, {
            "sh603259": {"error": "日线接口不可用"},
            "sh000001": {"error": "日线接口不可用"},
        })

        self.assertIn("日线接口不可用", states[0]["status"])
        self.assertIn("大盘上证日线接口不可用", states[0]["status"])

    # ---- 集合竞价成交判断 ----

    def test_quote_has_trade_false_when_zero_volume_and_amount(self):
        self.assertFalse(quote_has_trade({"price": 120.0, "volume": 0, "amount": 0}))
        self.assertFalse(quote_has_trade({"price": 120.0, "volume": 0.0, "amount": 0.0}))

    def test_quote_has_trade_true_when_volume_or_amount_positive(self):
        self.assertTrue(quote_has_trade({"price": 120.0, "volume": 12345, "amount": 0}))
        self.assertTrue(quote_has_trade({"price": 120.0, "volume": 0, "amount": 1.5e6}))

    def test_quote_has_trade_true_when_fields_missing(self):
        # 数据源缺 volume/amount 字段时保守视为已成交，避免策略失效
        self.assertTrue(quote_has_trade({"price": 120.0}))
        self.assertTrue(quote_has_trade({}))

    def test_strategy_position_state_skips_auction_price_before_trade(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
        })
        # 竞价未成交：价格 120 不应计入 peak/lock
        updated, changed = update_strategy_position_state(config, {
            "sh603259": {"price": 120.0, "name": "药明康德", "volume": 0, "amount": 0},
        })

        self.assertTrue(changed)
        self.assertTrue(updated["positions"][0]["auction_pending"])
        self.assertEqual(updated["positions"][0].get("peak_profit_pct", 0.0), 0.0)
        self.assertEqual(updated["positions"][0].get("locked_profit_pct", 0.0), 0.0)

    def test_strategy_position_state_recovers_after_first_trade(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
        })
        # 竞价阶段未成交
        updated, _ = update_strategy_position_state(config, {
            "sh603259": {"price": 120.0, "volume": 0, "amount": 0},
        })
        self.assertTrue(updated["positions"][0]["auction_pending"])
        # 第一笔成交后恢复计算
        updated2, changed = update_strategy_position_state(updated, {
            "sh603259": {"price": 120.0, "volume": 5000, "amount": 600000.0},
        })

        self.assertTrue(changed)
        self.assertFalse(updated2["positions"][0].get("auction_pending"))
        self.assertEqual(updated2["positions"][0]["peak_profit_pct"], 20.0)
        self.assertEqual(updated2["positions"][0]["locked_profit_pct"], 10.0)

    def test_strategy_alerts_not_triggered_during_auction_before_trade(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
        })
        # 价格跌到 90（-10%）但未成交：不应触发止损
        states = evaluate_strategy_alerts(config, {
            "sh603259": {"price": 90.0, "name": "药明康德", "volume": 0, "amount": 0},
        })

        self.assertEqual(len(states), 1)
        self.assertTrue(states[0]["auction_pending"])
        self.assertFalse(states[0]["triggered"])
        self.assertEqual(states[0]["severity"], "neutral")
        self.assertEqual(states[0]["status"], "竞价未成交")

    def test_strategy_alerts_trigger_normally_after_trade(self):
        config = normalize_strategy_alert_config({
            "enabled": True,
            "positions": [{"code": "603259", "cost_price": 100.0}],
        })
        states = evaluate_strategy_alerts(config, {
            "sh603259": {"price": 90.0, "name": "药明康德", "volume": 5000, "amount": 450000.0},
        })

        self.assertFalse(states[0].get("auction_pending"))
        self.assertTrue(states[0]["triggered"])
        self.assertEqual(states[0]["severity"], "danger")
        self.assertIn("触发止损", states[0]["status"])


if __name__ == "__main__":
    unittest.main()
