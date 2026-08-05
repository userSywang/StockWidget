import os
import unittest
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
        self.assertEqual(stock_row[STRATEGY_HEADERS.index("策略状态")], "已锁盈10%")

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


if __name__ == "__main__":
    unittest.main()
