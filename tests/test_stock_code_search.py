import unittest

from StockCodeSearch import resolve_stock_code


class StockCodeSearchTests(unittest.TestCase):
    def test_resolve_stock_code_matches_cached_full_name(self):
        code = resolve_stock_code("药明康德", {"sh603259": "药明康德"})

        self.assertEqual(code, "sh603259")

    def test_resolve_stock_code_matches_builtin_common_name(self):
        self.assertEqual(resolve_stock_code("兆易创新"), "sh603986")

    def test_resolve_stock_code_prefers_exact_name_over_contains(self):
        code = resolve_stock_code("药明康德", {
            "sh600000": "药明康德测试",
            "sh603259": "药明康德",
        })

        self.assertEqual(code, "sh603259")

    def test_resolve_stock_code_with_code_index_full_name(self):
        code_index = {
            "sh600000": {"code": "sh600000", "market": "sh", "name": "浦发银行"},
            "sh600519": {"code": "sh600519", "market": "sh", "name": "贵州茅台"},
        }

        self.assertEqual(resolve_stock_code("浦发银行", code_index=code_index), "sh600000")
        self.assertEqual(resolve_stock_code("贵州茅台", code_index=code_index), "sh600519")

    def test_resolve_stock_code_with_code_index_short_name(self):
        code_index = {
            "sh600519": {"code": "sh600519", "market": "sh", "name": "贵州茅台"},
            "sz000001": {"code": "sz000001", "market": "sz", "name": "平安银行"},
        }

        self.assertEqual(resolve_stock_code("茅台", code_index=code_index), "sh600519")
        self.assertEqual(resolve_stock_code("平安", code_index=code_index), "sz000001")

    def test_resolve_stock_code_prefers_exact_name_over_prefix_in_index(self):
        code_index = {
            "sh600000": {"code": "sh600000", "market": "sh", "name": "药明康德控股"},
            "sh603259": {"code": "sh603259", "market": "sh", "name": "药明康德"},
        }

        self.assertEqual(resolve_stock_code("药明康德", code_index=code_index), "sh603259")

    def test_resolve_stock_code_prefers_numeric_code_over_name(self):
        code_index = {
            "sh600000": {"code": "sh600000", "market": "sh", "name": "浦发银行"},
            "sz000001": {"code": "sz000001", "market": "sz", "name": "平安银行"},
        }

        self.assertEqual(resolve_stock_code("600000", code_index=code_index), "sh600000")
        self.assertEqual(resolve_stock_code("000001", code_index=code_index), "sz000001")


if __name__ == "__main__":
    unittest.main()
