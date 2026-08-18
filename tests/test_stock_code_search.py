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


if __name__ == "__main__":
    unittest.main()
