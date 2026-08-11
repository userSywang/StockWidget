import os
import unittest
from datetime import date, datetime
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHeaderView
from WidgetPanel import FloatLabel


BASE_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线"]
STRATEGY_HEADERS = BASE_HEADERS + ["MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"]


class WidgetPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_compose_display_rows_separates_alert_and_warning_sections(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线"]
        win.groups = [{"name": "科技ETF", "codes": ["sh512000"]}]
        win.checked_codes = ["sh512000"]
        win.warning_visible = True
        win.warning_text = "谨慎交易"

        rows, meta = FloatLabel._compose_display_rows(
            win,
            {"sh512000": ["sh512000", "券商ETF", "1.000", "+0.010", "+1.00%", "-", "-", "-", "-", "-", "1.000", ""]},
            {"sh512000": {"delta": 1}},
            [{"rule": {"name": "共振", "display_mode": "always"}, "status": "未触发", "triggered": False, "text": ""}],
        )

        self.assertEqual(meta[0]["row_type"], "group")
        self.assertEqual(meta[2]["row_type"], "separator")
        self.assertEqual(meta[3]["row_type"], "alert")
        self.assertEqual(meta[4]["row_type"], "separator")
        self.assertEqual(meta[5]["row_type"], "warning")
        self.assertEqual(rows[5][0], "谨慎交易")

    def test_compose_display_rows_attaches_price_alerts_to_stock_row(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线"]
        win.groups = [{"name": "ETF", "codes": ["sh512000"]}]
        win.checked_codes = ["sh512000"]
        win.warning_visible = False
        win.warning_text = ""

        _, meta = FloatLabel._compose_display_rows(
            win,
            {"sh512000": ["sh512000", "券商ETF", "1.200", "+0.010", "+1.00%", "-", "-", "-", "-", "-", "1.200", ""]},
            {"sh512000": {"delta": 1}},
            [],
            {"sh512000": [{"detail": "价格提醒"}]},
        )

        self.assertEqual(meta[1]["price_alerts"][0]["detail"], "价格提醒")

    def test_compose_display_rows_adds_market_amount_summary(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线"]
        win.groups = [{"name": "指数", "codes": ["sh000001"]}]
        win.checked_codes = ["sh000001"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = True

        rows, meta = FloatLabel._compose_display_rows(
            win,
            {
                "sh000001": ["sh000001", "上证指数", "1.00", "+0.00", "+0.00%", "-", "-", "-", "-", "8262.78亿", "-", ""],
                "sz399001": ["sz399001", "深证成指", "1.00", "+0.00", "+0.00%", "-", "-", "-", "-", "9717.22亿", "-", ""],
            },
            {"sh000001": {"delta": 0}, "sz399001": {"delta": 0}},
            [],
            {},
            {
                "sh000001": {"amount": 826278000000},
                "sz399001": {"amount": 971722000000},
            },
        )

        self.assertEqual(meta[2]["row_type"], "separator")
        self.assertEqual(meta[3]["row_type"], "market_amount")
        self.assertEqual(rows[3][0], "沪深成交额估算：17980.00亿")

    def test_get_price_uses_custom_json_data_source(self):
        class FakeResponse:
            def json(self):
                return {
                    "data": [
                        {
                            "code": "sh600000",
                            "name": "浦发银行",
                            "price": 10.23,
                            "change": 0.12,
                            "change_pct": 1.19,
                            "volume": 123456,
                            "amount": 1260000,
                        }
                    ]
                }

        class FakeHttp:
            def __init__(self):
                self.calls = []

            def get(self, url, headers=None, timeout=None):
                self.calls.append((url, headers, timeout))
                return FakeResponse()

        cfg = {
            "groups": [{"name": "自定义", "codes": ["sh600000"]}],
            "checked_codes": ["sh600000"],
            "data_source": {
                "mode": "custom",
                "url_template": "https://example.test/quote?codes={codes}",
                "headers": {"Authorization": "Bearer test-token"},
            },
        }
        with patch.object(FloatLabel, "_register_hotkey"), patch.object(FloatLabel, "_refresh_from_function"):
            win = FloatLabel(cfg)
        try:
            fake_http = FakeHttp()
            win._http = fake_http

            row_by_code, sign_by_code, quote_by_code = win._get_price(["sh600000"])

            self.assertEqual(fake_http.calls[0][0], "https://example.test/quote?codes=sh600000")
            self.assertEqual(fake_http.calls[0][1]["Authorization"], "Bearer test-token")
            self.assertEqual(row_by_code["sh600000"][1], "浦发银行")
            self.assertEqual(row_by_code["sh600000"][2], "10.23 ")
            self.assertEqual(sign_by_code["sh600000"]["delta"], 1)
            self.assertEqual(quote_by_code["sh600000"]["change_pct"], 1.19)
        finally:
            win.timer.stop()
            win._keep_top_timer.stop()
            win.shutdown_background()
            win.close()

    def test_current_config_persists_code_tags(self):
        cfg = {
            "groups": [{"name": "默认", "codes": ["sh603259"]}],
            "checked_codes": ["sh603259"],
            "code_tags": {
                "sh603259": {"holding": "hold", "cycle": "short", "priority": "focus"}
            },
            "price_alert_badge_visible": False,
        }
        with patch.object(FloatLabel, "_register_hotkey"), patch.object(FloatLabel, "_refresh_from_function"):
            win = FloatLabel(cfg)
        try:
            self.assertEqual(win.code_tags["sh603259"]["holding"], "hold")
            self.assertEqual(win.current_config()["code_tags"]["sh603259"]["cycle"], "short")
            self.assertFalse(win.current_config()["price_alert_badge_visible"])
        finally:
            win.timer.stop()
            win._keep_top_timer.stop()
            win.shutdown_background()
            win.close()

    def test_current_config_persists_strategy_alert_history(self):
        cfg = {
            "strategy_alert_history": [{
                "time": "2026-08-10 10:00",
                "code": "603259",
                "name": "药明康德",
                "status": "触发止损",
                "severity": "danger",
            }],
        }
        with patch.object(FloatLabel, "_register_hotkey"), patch.object(FloatLabel, "_refresh_from_function"):
            win = FloatLabel(cfg)
        try:
            self.assertEqual(win.strategy_alert_history[0]["code"], "sh603259")
            self.assertEqual(win.current_config()["strategy_alert_history"][0]["status"], "触发止损")
        finally:
            win.timer.stop()
            win._keep_top_timer.stop()
            win.shutdown_background()
            win.close()

    def test_refresh_request_codes_include_market_amount_indexes(self):
        win = FloatLabel.__new__(FloatLabel)
        win.checked_codes = ["sh600000"]
        win.market_amount_visible = True
        win._alert_request_codes = lambda: []
        win._strategy_request_codes = lambda: []

        codes = FloatLabel._refresh_request_codes(win)

        self.assertEqual(codes, ["sh600000", "sh000001", "sz399001"])

    def test_refresh_request_codes_include_strategy_positions(self):
        win = FloatLabel.__new__(FloatLabel)
        win.checked_codes = ["sh600000"]
        win.market_amount_visible = False
        win._alert_request_codes = lambda: []
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "512000", "cost_price": 1.0}],
        }

        codes = FloatLabel._refresh_request_codes(win)

        self.assertEqual(codes, ["sh600000", "sh512000", "sh000001", "sz399001"])

    def test_daily_request_codes_include_price_alert_below_ma5(self):
        win = FloatLabel.__new__(FloatLabel)
        win.checked_codes = ["sh600000"]
        win.price_alerts = [{"enabled": True, "code": "sh603259", "direction": "below_ma5"}]
        win.ma5_visible = False
        win.ma10_visible = False
        win.ma20_visible = False
        win.strategy_alert_config = {"enabled": False}

        codes = FloatLabel._daily_request_codes(win)

        self.assertEqual(codes, ["sh603259"])

    def test_market_fetch_time_only_allows_9_to_15_on_weekdays(self):
        win = FloatLabel.__new__(FloatLabel)

        self.assertTrue(FloatLabel._is_market_fetch_time(win, datetime(2026, 8, 11, 9, 0)))
        self.assertTrue(FloatLabel._is_market_fetch_time(win, datetime(2026, 8, 11, 15, 0)))
        self.assertFalse(FloatLabel._is_market_fetch_time(win, datetime(2026, 8, 11, 23, 0)))
        self.assertFalse(FloatLabel._is_market_fetch_time(win, datetime(2026, 8, 15, 10, 0)))

    def test_refresh_outside_market_skips_network_but_checks_daily_summary(self):
        win = FloatLabel.__new__(FloatLabel)
        win._now = lambda: datetime(2026, 8, 11, 23, 0)
        win._refresh_future = None
        win._refresh_again_requested = False
        calls = []
        win._get_refresh_data = lambda *_args: (_ for _ in ()).throw(AssertionError("network fetch should be skipped"))
        win._check_strategy_daily_summary = lambda: calls.append("summary") or True

        FloatLabel._refresh_from_function(win)

        self.assertEqual(calls, ["summary"])

    def test_daily_summary_check_uses_latest_strategy_states_outside_market(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._now = lambda: datetime(2026, 8, 11, 23, 0)
        win._strategy_daily_summary_sent_date = ""
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
                "daily_summary_time": "23:00",
            },
        }
        win._latest_strategy_states = [
            {"code": "sh603259", "name": "药明康德", "profit_pct": 1.0, "locked_profit_pct": 0.0, "status": "未触发"},
            {"code": "sh600584", "name": "长电科技", "profit_pct": -1.0, "locked_profit_pct": 0.0, "status": "未触发"},
        ]

        sent = FloatLabel._check_strategy_daily_summary(win)

        self.assertTrue(sent)
        self.assertEqual(len(win._http.posts), 1)
        content = win._http.posts[0][1]["markdown"]["content"]
        self.assertIn("sh603259", content)
        self.assertIn("sh600584", content)

    def test_get_daily_klines_uses_baostock_rows_first(self):
        win = FloatLabel.__new__(FloatLabel)
        win._get_baostock_daily_klines = lambda *_args: [
            {"date": "2026-08-01", "close": 10.2},
            {"date": "2026-08-02", "close": 10.5},
        ]
        win._get_tencent_daily_klines = lambda *_args: (_ for _ in ()).throw(Exception("should not call tencent"))
        win._get_eastmoney_daily_klines = lambda *_args: (_ for _ in ()).throw(Exception("should not call eastmoney"))
        win._daily_kline_cache = {}

        daily = FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)

        self.assertEqual(daily["sh000001"][0]["date"], "2026-08-01")
        self.assertEqual(daily["sh000001"][1]["close"], 10.5)

    def test_get_daily_klines_falls_back_to_tencent_rows(self):
        class FakeResponse:
            def json(self):
                return {
                    "code": 0,
                    "data": {
                        "sh000001": {
                            "qfqday": [
                                ["2026-08-01", "10.00", "10.20", "10.30", "9.90", "1000"],
                                ["2026-08-02", "10.20", "10.50", "10.60", "10.10", "1100"],
                            ]
                        }
                    },
                }

        class FakeHttp:
            def __init__(self):
                self.urls = []

            def get(self, url, headers=None, timeout=None):
                self.urls.append(url)
                return FakeResponse()

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._get_baostock_daily_klines = lambda *_args: []
        win._daily_kline_cache = {}

        daily = FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)

        self.assertIn("web.ifzq.gtimg.cn", win._http.urls[0])
        self.assertEqual(len(win._http.urls), 1)
        self.assertEqual(daily["sh000001"][0]["date"], "2026-08-01")
        self.assertEqual(daily["sh000001"][1]["close"], 10.5)

    def test_get_daily_klines_reuses_daily_cache(self):
        win = FloatLabel.__new__(FloatLabel)
        calls = []

        def fake_baostock(*_args):
            calls.append("baostock")
            return [
                {"date": "2026-08-01", "close": 10.2},
                {"date": "2026-08-02", "close": 10.5},
            ]

        win._get_baostock_daily_klines = fake_baostock
        win._get_tencent_daily_klines = lambda *_args: []
        win._get_eastmoney_daily_klines = lambda *_args: []
        win._daily_kline_cache = {}

        FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)
        daily = FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)

        self.assertEqual(calls, ["baostock"])
        self.assertEqual(daily["sh000001"][1]["close"], 10.5)

    def test_get_daily_klines_refreshes_cache_on_new_day(self):
        win = FloatLabel.__new__(FloatLabel)
        calls = []
        today_values = [date(2026, 8, 10), date(2026, 8, 11)]
        win._today = lambda: today_values[min(len(calls), len(today_values) - 1)]

        def fake_baostock(*_args):
            calls.append("baostock")
            close = 10.0 + len(calls)
            return [
                {"date": "2026-08-01", "close": close},
                {"date": "2026-08-02", "close": close + 0.5},
            ]

        win._get_baostock_daily_klines = fake_baostock
        win._get_tencent_daily_klines = lambda *_args: []
        win._get_eastmoney_daily_klines = lambda *_args: []
        win._daily_kline_cache = {}

        FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)
        daily = FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)

        self.assertEqual(calls, ["baostock", "baostock"])
        self.assertEqual(daily["sh000001"][1]["close"], 12.5)

    def test_daily_rows_use_realtime_price_for_today_ma(self):
        win = FloatLabel.__new__(FloatLabel)
        win._today = lambda: date(2026, 8, 10)
        rows = [{"date": f"2026-08-0{i}", "close": float(i)} for i in range(1, 6)]

        daily = FloatLabel._daily_rows_with_realtime_price(
            win,
            {"sh603259": rows},
            {"sh603259": {"price": 20.0}},
        )

        self.assertEqual(daily["sh603259"][-1]["date"], "2026-08-10")
        self.assertEqual(daily["sh603259"][-1]["close"], 20.0)
        self.assertTrue(daily["sh603259"][-1]["realtime"])
        self.assertEqual(daily["sh603259"][-5:], rows[1:] + [daily["sh603259"][-1]])
        self.assertEqual(sum(row["close"] for row in daily["sh603259"][-5:]) / 5, 6.8)

    def test_daily_rows_replace_today_close_with_realtime_price(self):
        win = FloatLabel.__new__(FloatLabel)
        win._today = lambda: date(2026, 8, 10)
        rows = [{"date": "2026-08-10", "close": 10.0, "high": 11.0, "low": 9.0}]

        daily = FloatLabel._daily_rows_with_realtime_price(
            win,
            {"sh603259": rows},
            {"sh603259": {"price": 12.0}},
        )

        self.assertEqual(daily["sh603259"][-1]["close"], 12.0)
        self.assertEqual(daily["sh603259"][-1]["high"], 12.0)
        self.assertTrue(daily["sh603259"][-1]["realtime"])

    def test_get_daily_klines_falls_back_to_eastmoney_rows(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        class FakeHttp:
            def __init__(self):
                self.urls = []

            def get(self, url, headers=None, timeout=None):
                self.urls.append(url)
                if "web.ifzq.gtimg.cn" in url:
                    return FakeResponse({"code": 0, "data": {"sh000001": {}}})
                return FakeResponse({
                    "data": {
                        "klines": [
                            "2026-08-01,10.00,10.20,10.30,9.90,1000,2000",
                            "2026-08-02,10.20,10.50,10.60,10.10,1100,2300",
                        ]
                    }
                })

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._get_baostock_daily_klines = lambda *_args: []
        win._daily_kline_cache = {}

        daily = FloatLabel._get_daily_klines(win, ["sh000001"], limit=2)

        self.assertIn("web.ifzq.gtimg.cn", win._http.urls[0])
        self.assertIn("secid=1.000001", win._http.urls[1])
        self.assertEqual(daily["sh000001"][0]["date"], "2026-08-01")
        self.assertEqual(daily["sh000001"][1]["close"], 10.5)

    def test_get_daily_klines_parses_baostock_rows(self):
        class FakeLogin:
            error_code = "0"
            error_msg = ""

        class FakeResult:
            error_code = "0"
            error_msg = ""
            fields = ["date", "code", "open", "high", "low", "close", "volume", "amount"]

            def __init__(self):
                self.rows = [
                    ["2026-08-01", "sh.000001", "10.00", "10.30", "9.90", "10.20", "1000", "2000"],
                    ["2026-08-02", "sh.000001", "10.20", "10.60", "10.10", "10.50", "1100", "2300"],
                ]
                self.index = -1

            def next(self):
                self.index += 1
                return self.index < len(self.rows)

            def get_row_data(self):
                return self.rows[self.index]

        class FakeBaostock:
            def __init__(self):
                self.queries = []
                self.logout_called = False

            def login(self):
                return FakeLogin()

            def query_history_k_data_plus(self, *args, **kwargs):
                self.queries.append((args, kwargs))
                return FakeResult()

            def logout(self):
                self.logout_called = True

        fake_bs = FakeBaostock()
        win = FloatLabel.__new__(FloatLabel)

        with patch.dict("sys.modules", {"baostock": fake_bs}):
            rows = FloatLabel._get_baostock_daily_klines(win, "sh000001", limit=2)

        self.assertEqual(fake_bs.queries[0][0][0], "sh.000001")
        self.assertEqual(rows[0]["date"], "2026-08-01")
        self.assertEqual(rows[0]["open"], 10.0)
        self.assertEqual(rows[1]["close"], 10.5)
        self.assertEqual(rows[1]["amount"], 2300.0)
        self.assertTrue(fake_bs.logout_called)

    def test_get_daily_klines_marks_source_unavailable(self):
        win = FloatLabel.__new__(FloatLabel)
        win._get_tencent_daily_klines = lambda *_args: (_ for _ in ()).throw(Exception("blocked"))
        win._get_eastmoney_daily_klines = lambda *_args: (_ for _ in ()).throw(Exception("blocked"))
        win._get_baostock_daily_klines = lambda *_args: (_ for _ in ()).throw(Exception("blocked"))

        daily = FloatLabel._get_daily_klines(win, ["sh603259"], limit=20)

        self.assertEqual(daily["sh603259"]["error"], "日线接口不可用")

    def test_compose_strategy_rows_shows_triggered_status(self):
        win = FloatLabel.__new__(FloatLabel)

        rows, meta = FloatLabel._compose_strategy_rows(
            win,
            [{
                "name": "券商ETF",
                "profit_pct": 9.0,
                "locked_profit_pct": 10.0,
                "stop_price": 1.1,
                "ma5": 1.05,
                "ma10": 1.03,
                "ma20": 1.01,
                "enabled_rules": ["止损", "个股MA5"],
                "triggered": True,
                "severity": "danger",
                "status": "触发锁盈10%",
            }],
        )

        self.assertEqual(rows[0], ["券商ETF", "盈亏 +9.0%", "止损 1.10", "触发锁盈10%"])
        self.assertEqual(rows[1], ["", "MA5 1.05", "MA10 1.03", "MA20 1.01"])
        self.assertTrue(meta[0]["triggered"])
        self.assertTrue(meta[1]["strategy_detail"])
        self.assertEqual(meta[0]["severity"], "danger")

    def test_apply_refresh_result_notifies_when_code_names_are_learned(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = BASE_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh512000"]}]
        win.checked_codes = ["sh512000"]
        win.alert_rules = []
        win.price_alerts = []
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.code_names = {}
        win._refresh_again_requested = False
        changes = []
        win._on_change = lambda: changes.append("saved")
        win._project_columns = lambda *_args: None
        row = ["sh512000", "券商ETF", "1.000", "+0.000", "+0.00%", "-", "-", "-", "0", "0", "1.000", ""]

        FloatLabel._apply_refresh_result(
            win,
            {"sh512000": row},
            {"sh512000": {"delta": 0}},
            {"sh512000": {"name": "券商ETF", "price": 1.0}},
            {},
        )

        self.assertEqual(win.code_names["sh512000"], "券商ETF")
        self.assertEqual(changes, ["saved"])

    def test_compose_display_rows_adds_ma_and_strategy_fields(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.strategy_alert_config = {"enabled": True}
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]
        daily_rows = [{"close": float(v)} for v in range(1, 21)]
        strategy_states = [{
            "code": "sh603259",
            "profit_pct": 12.0,
            "stop_price": 110.0,
            "status": "已锁盈10%",
            "daily_date": "2026-08-10",
            "daily_realtime": True,
        }]

        rows, _meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {},
            {"sh603259": {"price": 112.0}},
            {"sh603259": daily_rows},
            strategy_states,
        )

        stock_row = rows[1]
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("MA5")], "18.00")
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("MA10")], "15.50")
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("MA20")], "10.50")
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("持仓盈亏")], "+12.0%")
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("止损线")], "110.00")
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("策略状态")], "已锁盈10% | 实时08-10")

    def test_compose_display_rows_appends_code_tags_to_name(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.strategy_alert_config = {"enabled": False}
        win.code_tags = {
            "sh603259": {"holding": "hold", "cycle": "short", "priority": "focus"}
        }
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, _meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {},
            {"sh603259": {"price": 112.0}},
            {},
            [],
        )

        stock_row = rows[1]
        name_text = stock_row[STRATEGY_HEADERS.index("名称")]
        self.assertIn("药明康德", name_text)
        self.assertIn("[持有/短线/重点]", name_text)

    def test_compose_display_rows_appends_code_tags_to_code_when_name_hidden(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.strategy_alert_config = {"enabled": False}
        win.code_tags = {
            "sh603259": {"holding": "hold", "cycle": "long", "priority": "focus"}
        }
        win.header_is_visible = lambda header: header != "名称"
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, _meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {},
            {"sh603259": {"price": 112.0}},
            {},
            [],
        )

        stock_row = rows[1]
        code_text = stock_row[STRATEGY_HEADERS.index("代码")]
        self.assertIn("sh603259", code_text)
        self.assertIn("[持有/长期/重点]", code_text)

    def test_compose_display_rows_prioritizes_strategy_badge_over_price_alert(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.strategy_alert_config = {"enabled": True}
        win.code_tags = {}
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {"sh603259": [{"triggered": True, "detail": "价格提醒"}]},
            {"sh603259": {"price": 112.0}},
            {},
            [{"code": "sh603259", "triggered": True, "severity": "danger", "status": "触发止损"}],
        )

        stock_row = rows[1]
        name_text = stock_row[STRATEGY_HEADERS.index("名称")]
        self.assertIn("[策略]", name_text)
        self.assertNotIn("价警/策略", name_text)
        self.assertTrue(meta[1]["strategy"])
        self.assertEqual(meta[1]["severity"], "danger")
        self.assertTrue(meta[1]["price_alerts"][0]["triggered"])

    def test_compose_display_rows_shows_price_alert_badge_without_strategy_trigger(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.strategy_alert_config = {"enabled": True}
        win.code_tags = {}
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {"sh603259": [{"triggered": True, "detail": "价格提醒"}]},
            {"sh603259": {"price": 112.0}},
            {},
            [{"code": "sh603259", "triggered": False, "severity": "neutral", "status": "未触发"}],
        )

        stock_row = rows[1]
        name_text = stock_row[STRATEGY_HEADERS.index("名称")]
        self.assertIn("[价警]", name_text)
        self.assertTrue(meta[1]["price_alerts"][0]["triggered"])

    def test_compose_display_rows_hides_price_alert_badge_when_disabled(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        win.price_alert_badge_visible = False
        win.strategy_alert_config = {"enabled": True}
        win.code_tags = {}
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {"sh603259": [{"triggered": True, "detail": "价格提醒"}]},
            {"sh603259": {"price": 112.0}},
            {},
            [{"code": "sh603259", "triggered": False, "severity": "neutral", "status": "未触发"}],
        )

        stock_row = rows[1]
        name_text = stock_row[STRATEGY_HEADERS.index("名称")]
        self.assertNotIn("[价警]", name_text)
        self.assertNotIn("price_alerts", meta[1])

    def test_compose_display_rows_shows_dash_for_undefined_strategy_fields(self):
        win = FloatLabel.__new__(FloatLabel)
        win.ALL_HEADERS = STRATEGY_HEADERS
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.warning_visible = False
        win.warning_text = ""
        win.market_amount_visible = False
        row = ["sh603259", "药明康德", "112.00", "+12.00", "+12.00%", "-", "-", "-", "0", "0", "112.00", ""]

        rows, _meta = FloatLabel._compose_display_rows(
            win,
            {"sh603259": row},
            {"sh603259": {"delta": 1}},
            [],
            {},
            {"sh603259": {"price": 112.0}},
            {"sh603259": [{"error": "日线接口不可用"}]},
            [],
        )

        stock_row = rows[1]
        for header in ("MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"):
            self.assertEqual(stock_row[STRATEGY_HEADERS.index(header)], "-")

    def test_strategy_push_payload_uses_wecom_markdown(self):
        win = FloatLabel.__new__(FloatLabel)
        win.strategy_alert_config = {
            "notifications": {"remote_push": True, "remote_channel": "wecom", "webhook_url": "https://example.test"},
        }

        payload = FloatLabel._strategy_push_payload(win, "测试内容")

        self.assertEqual(payload, {"msgtype": "markdown", "markdown": {"content": "测试内容"}})

    def test_compact_desktop_alert_text_keeps_key_lines(self):
        text = FloatLabel._compact_desktop_alert_text(
            "## 药明康德止盈线变化\n"
            ">标的：药明康德\n"
            ">代码：sh603259\n"
            ">变动：\n"
            ">成本价：100.000 -> 120.000\n"
            ">止盈线：110.00 -> 132.00\n"
            ">备注：不会显示"
        )

        self.assertIn("药明康德止盈线变化", text)
        self.assertIn("标的：药明康德", text)
        self.assertIn("代码：sh603259", text)
        self.assertIn("变动：", text)
        self.assertIn("成本价：100.000 -> 120.000", text)
        self.assertIn("止盈线：110.00 -> 132.00", text)
        self.assertNotIn("备注", text)

    def test_desktop_alert_keeps_latest_three_until_closed(self):
        win = FloatLabel({
            "codes": ["sh603259"],
            "checked_codes": ["sh603259"],
            "strategy_alerts": {
                "notifications": {"desktop_popup": True},
            },
        })
        try:
            win.setGeometry(100, 200, 260, 80)
            for idx in range(4):
                win.show_desktop_alert(f"## 股票{idx}策略触发\n>标的：股票{idx}\n>代码：sh00000{idx}\n>状态：测试")

            toasts = getattr(win, "_alert_toasts", [])
            self.assertEqual(len(toasts), 3)
            labels = [toast._message_label.text() for toast in toasts]
            self.assertNotIn("股票0", "\n".join(labels))
            self.assertIn("股票1", labels[0])
            self.assertIn("股票3", labels[-1])
            self.assertFalse(hasattr(win, "_alert_toast_timer"))

            win._close_alert_toast(toasts[-1])
            self.assertEqual(len(getattr(win, "_alert_toasts", [])), 2)
        finally:
            for toast in list(getattr(win, "_alert_toasts", [])):
                toast.hide()
                toast.deleteLater()
            win.close()

    def test_desktop_alert_ignore_today_suppresses_same_key(self):
        win = FloatLabel({
            "codes": ["sh603259"],
            "checked_codes": ["sh603259"],
            "strategy_alerts": {
                "notifications": {"desktop_popup": True},
            },
        })
        try:
            win.setGeometry(100, 200, 260, 80)
            win.show_desktop_alert("## 药明康德止损触发\n>代码：sh603259", ignore_key="sh603259|止损")

            toasts = getattr(win, "_alert_toasts", [])
            self.assertEqual(len(toasts), 1)
            self.assertFalse(toasts[0]._ignore_button.isHidden())

            toasts[0]._ignore_button.click()
            self.assertEqual(len(getattr(win, "_alert_toasts", [])), 0)

            win.show_desktop_alert("## 药明康德止损触发\n>代码：sh603259", ignore_key="sh603259|止损")
            self.assertEqual(len(getattr(win, "_alert_toasts", [])), 0)

            win.show_desktop_alert("## 药明康德止盈触发\n>代码：sh603259", ignore_key="sh603259|止盈")
            self.assertEqual(len(getattr(win, "_alert_toasts", [])), 1)
        finally:
            for toast in list(getattr(win, "_alert_toasts", [])):
                toast.hide()
                toast.deleteLater()
            win.close()

    def test_strategy_push_text_includes_stop_price_and_raised_status(self):
        win = FloatLabel.__new__(FloatLabel)
        text = FloatLabel._strategy_push_text_for_state(win, {
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": 20.0,
            "locked_profit_pct": 10.0,
            "stop_price": 110.0,
            "status": "上调止盈线至110.00",
        })

        self.assertIn("## 药明康德止盈触发", text)
        self.assertIn("标的：药明康德", text)
        self.assertIn("止盈线：110.00（锁盈+10.0%）", text)
        self.assertIn("上调止盈线至110.00", text)
        self.assertNotIn("StockWidget", text)
        self.assertNotIn("重要提醒", text)
        self.assertNotIn("止盈/止损线", text)

    def test_strategy_push_text_includes_changed_stop_line_prices(self):
        win = FloatLabel.__new__(FloatLabel)
        text = FloatLabel._strategy_push_text_for_state(win, {
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": 15.0,
            "locked_profit_pct": 10.0,
            "stop_price": 110.0,
            "take_profit_price": 110.0,
            "stop_line_changed": True,
            "stop_line_previous_price": 109.0,
            "status": "止盈线变动至110.00",
        })

        self.assertIn("## 药明康德止盈线变化", text)
        self.assertIn("变动：", text)
        self.assertIn("止盈线：109.00 -> 110.00", text)
        self.assertIn("状态：止盈线变动至110.00", text)

    def test_strategy_push_text_uses_stop_loss_label_without_locked_profit(self):
        win = FloatLabel.__new__(FloatLabel)
        text = FloatLabel._strategy_push_text_for_state(win, {
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": -5.0,
            "locked_profit_pct": 0.0,
            "stop_price": 95.0,
            "stop_line_changed": True,
            "stop_line_previous_price": 96.0,
            "status": "止损线变动至95.00",
        })

        self.assertIn("## 药明康德止损线变化", text)
        self.assertIn("止损线：96.00 -> 95.00", text)
        self.assertNotIn("止盈线：96.00 -> 95.00", text)

    def test_strategy_push_text_includes_triggered_action_lines(self):
        win = FloatLabel.__new__(FloatLabel)
        text = FloatLabel._strategy_push_text_for_state(win, {
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": -6.0,
            "locked_profit_pct": 0.0,
            "stop_loss_price": 95.0,
            "status": "触发止损",
            "triggered_actions": [{
                "rule_id": "max_loss",
                "rule_name": "浮亏清仓",
                "action_type": "clear_position",
                "details": {"stop_loss_price": 95.0, "threshold_pct": -5.0},
            }],
        })

        self.assertIn(">动作：", text)
        self.assertIn(">浮亏清仓：止损价95.00，阈值-5.0%", text)

    def test_strategy_push_payload_uses_custom_json(self):
        win = FloatLabel.__new__(FloatLabel)
        win.strategy_alert_config = {
            "notifications": {"remote_push": True, "remote_channel": "custom", "webhook_url": "https://example.test"},
        }

        payload = FloatLabel._strategy_push_payload(win, "测试内容")

        self.assertEqual(payload["source"], "StockWidget")
        self.assertEqual(payload["type"], "strategy_alert")
        self.assertEqual(payload["content"], "测试内容")

    def test_strategy_pushes_triggered_states_once(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._strategy_push_sent_keys = set()
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
            },
        }
        states = [{
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": -5.2,
            "locked_profit_pct": 0.0,
            "triggered": True,
            "status": "触发止损",
        }]

        FloatLabel._send_strategy_pushes(win, states)
        FloatLabel._send_strategy_pushes(win, states)

        self.assertEqual(len(win._http.posts), 1)
        self.assertEqual(win._http.posts[0][0], "https://example.test/webhook")
        self.assertIn("触发止损", win._http.posts[0][1]["markdown"]["content"])

    def test_price_alert_pushes_triggered_alerts_to_webhook(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._price_alert_push_sent_keys = set()
        win._price_alert_push_sent_at = {}
        win._now = lambda: datetime(2026, 8, 10, 10, 0)
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
                "push_cooldown_minutes": 30,
            },
        }
        alerts = {
            "sh603259": [{
                "triggered": True,
                "name": "药明康德",
                "direction": "below",
                "price": 145.0,
                "current_price": 144.5,
                "message": "跌破提醒",
            }]
        }

        pushed = FloatLabel._send_price_alert_pushes(win, alerts)
        pushed_again = FloatLabel._send_price_alert_pushes(win, alerts)

        self.assertTrue(pushed)
        self.assertFalse(pushed_again)
        self.assertEqual(len(win._http.posts), 1)
        content = win._http.posts[0][1]["markdown"]["content"]
        self.assertIn("药明康德价格提醒", content)
        self.assertIn("标的：药明康德", content)
        self.assertIn("当前价：144.500", content)
        self.assertIn("条件：低于/等于 145.000", content)

    def test_strategy_pushes_respects_cooldown_and_records_history(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._strategy_push_sent_keys = set()
        win._strategy_push_sent_at = {}
        win.strategy_alert_history = []
        changes = []
        win._on_change = lambda: changes.append("saved")
        win._now = lambda: datetime(2026, 8, 10, 10, 0)
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
                "push_cooldown_minutes": 30,
            },
        }
        state = {
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": -5.2,
            "locked_profit_pct": 0.0,
            "triggered": True,
            "severity": "danger",
            "status": "触发止损",
        }

        FloatLabel._send_strategy_pushes(win, [state])
        FloatLabel._send_strategy_pushes(win, [state])
        win._now = lambda: datetime(2026, 8, 10, 10, 31)
        FloatLabel._send_strategy_pushes(win, [state])

        self.assertEqual(len(win._http.posts), 2)
        self.assertEqual(win.strategy_alert_history[0]["time"], "2026-08-10 10:31")
        self.assertEqual(win.strategy_alert_history[0]["name"], "药明康德")
        self.assertEqual(changes, ["saved", "saved"])

    def test_strategy_pushes_raised_stop_line_state(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._strategy_push_sent_keys = set()
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
            },
        }
        states = [{
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": 20.0,
            "locked_profit_pct": 10.0,
            "stop_price": 110.0,
            "take_profit_price": 110.0,
            "triggered": True,
            "severity": "warning",
            "status": "上调止盈线至110.00",
        }]

        FloatLabel._send_strategy_pushes(win, states)

        self.assertEqual(len(win._http.posts), 1)
        content = win._http.posts[0][1]["markdown"]["content"]
        self.assertIn("上调止盈线至110.00", content)
        self.assertIn("止盈线：110.00", content)

    def test_strategy_daily_summary_sends_once_after_configured_time(self):
        class FakeHttp:
            def __init__(self):
                self.posts = []

            def post(self, url, json=None, timeout=None):
                self.posts.append((url, json, timeout))

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._strategy_daily_summary_sent_date = ""
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
                "daily_summary_time": "14:30",
            },
        }
        states = [{
            "code": "sh603259",
            "name": "药明康德",
            "profit_pct": 12.0,
            "locked_profit_pct": 10.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 110.0,
            "status": "已锁盈10%",
        }]
        now = datetime(2026, 8, 10, 14, 30)

        sent = FloatLabel._send_strategy_daily_summary(win, states, now)
        repeated = FloatLabel._send_strategy_daily_summary(win, states, now)

        self.assertTrue(sent)
        self.assertFalse(repeated)
        self.assertEqual(win._strategy_daily_summary_sent_date, "2026-08-10")
        self.assertEqual(len(win._http.posts), 1)
        content = win._http.posts[0][1]["markdown"]["content"]
        self.assertIn("策略定时摘要", content)
        self.assertIn("时间：2026-08-10 14:30", content)
        self.assertIn("标的：药明康德", content)
        self.assertIn("代码：sh603259", content)
        self.assertIn("止损线：95.00", content)
        self.assertIn("止盈线：110.00", content)

    def test_strategy_daily_summary_waits_until_configured_time(self):
        class FakeHttp:
            def post(self, *_args, **_kwargs):
                raise AssertionError("should not push before 11:00")

        win = FloatLabel.__new__(FloatLabel)
        win._http = FakeHttp()
        win._strategy_daily_summary_sent_date = ""
        win.strategy_alert_config = {
            "notifications": {
                "remote_push": True,
                "remote_channel": "wecom",
                "webhook_url": "https://example.test/webhook",
                "daily_summary_time": "23:00",
            },
        }

        sent = FloatLabel._send_strategy_daily_summary(
            win,
            [{"code": "sh603259", "name": "药明康德", "status": "未触发"}],
            datetime(2026, 8, 10, 22, 59),
        )

        self.assertFalse(sent)

    def test_column_width_sources_ignore_message_rows(self):
        rows = [
            ["科技ETF", "", ""],
            ["sh512000", "券商ETF", "1.200"],
            ["炒股祖训第一条：谨慎交易，不追高，不满仓，先确认再操作", "", ""],
        ]
        meta = [
            {"row_type": "group", "text": "科技ETF"},
            {},
            {"row_type": "warning", "text": "炒股祖训第一条：谨慎交易，不追高，不满仓，先确认再操作"},
        ]

        sources = FloatLabel._column_width_source_rows(rows, meta)

        self.assertEqual(sources, [rows[1]])

    def test_wrap_text_for_width_inserts_line_breaks(self):
        wrapped = FloatLabel._wrap_text_for_width(
            "炒股祖训谨慎交易",
            4,
            lambda text: len(text),
        )

        self.assertEqual(wrapped, "炒股祖训\n谨慎交易")

    def test_fit_uses_fixed_header_sections_so_message_rows_cannot_expand_columns(self):
        cfg = {
            "groups": [{"name": "指数", "codes": ["sh000001"]}],
            "checked_codes": ["sh000001"],
            "code_visible": True,
            "name_visible": True,
            "price_visible": True,
            "change_pct_visible": True,
            "b1s1_visible": True,
            "warning_visible": True,
            "warning_text": "炒股祖训：早上大跌要买，早上大涨要卖，下午大涨不追，下午大跌次日买。",
        }
        with patch.object(FloatLabel, "_register_hotkey"), patch.object(FloatLabel, "_refresh_from_function"):
            win = FloatLabel(cfg)
        try:
            row = [
                "sh000001", "上证指数", "3864.37", "+0.00", "+0.00%",
                "3864.00", "3864.50", "0.00%", "0", "0", "3864.37", "",
            ]
            full_rows, meta = win._compose_display_rows(
                {"sh000001": row},
                {"sh000001": {"delta": 0}},
                [],
            )
            win._project_columns(full_rows, meta)
            self.app.processEvents()

            self.assertEqual(
                win.table.horizontalHeader().sectionResizeMode(0),
                QHeaderView.Fixed,
            )

            width_with_order_book = win.width()
            win.b1s1_visible = False
            win._project_columns(full_rows, meta)
            self.app.processEvents()

            self.assertLess(win.width(), width_with_order_book)
            self.assertNotIn("买一", win.model._headers)
            self.assertNotIn("卖一", win.model._headers)
        finally:
            win.timer.stop()
            win._keep_top_timer.stop()
            win.shutdown_background()
            win.close()

    def test_project_columns_keeps_stock_identifier_when_code_and_name_are_hidden(self):
        cfg = {
            "groups": [{"name": "指数", "codes": ["sh000001"]}],
            "checked_codes": ["sh000001"],
            "code_visible": False,
            "name_visible": False,
            "price_visible": True,
        }
        with patch.object(FloatLabel, "_register_hotkey"), patch.object(FloatLabel, "_refresh_from_function"):
            win = FloatLabel(cfg)
        try:
            full_rows = [[
                "sh000001", "上证指数", "3864.37", "+0.00", "+0.00%",
                "3864.00", "3864.50", "0.00%", "0", "0", "3864.37", "",
            ]]
            win._project_columns(full_rows, [{}])

            self.assertIn("名称", win.model._headers)
            self.assertIn("现价", win.model._headers)
            self.assertEqual(win.model._rows[0][0], "上证指数")
        finally:
            win.timer.stop()
            win._keep_top_timer.stop()
            win.shutdown_background()
            win.close()


if __name__ == "__main__":
    unittest.main()
