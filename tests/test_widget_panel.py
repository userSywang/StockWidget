import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHeaderView
from WidgetPanel import FloatLabel


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

        codes = FloatLabel._refresh_request_codes(win)

        self.assertEqual(codes, ["sh600000", "sh000001", "sz399001"])

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
