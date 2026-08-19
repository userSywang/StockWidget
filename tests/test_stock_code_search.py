import json
import os
import tempfile
import unittest
from datetime import date, timedelta

from StockCodeSearch import (
    load_stock_code_index,
    refresh_code_index_from_remote,
    resolve_stock_code,
)


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


class RemoteIndexRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.tmp_dir.name, "stock_codes_list.json")
        self.addCleanup(self.tmp_dir.cleanup)

    def _write_cache(self, codes, updated_at):
        payload = {"codes": codes, "updated_at": updated_at}
        with open(self.cache_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)

    def _fake_response(self, payload, status_code=200):
        class FakeResponse:
            def __init__(self):
                self.status_code = status_code
                self.text = json.dumps(payload, ensure_ascii=False)

        return FakeResponse()

    def test_refresh_downloads_and_writes_cache(self):
        payload = {
            "codes": {"sh600000": {"code": "sh600000", "market": "sh", "name": "浦发银行"}},
            "updated_at": "2026-08-19 15:30:00",
        }
        calls = []

        def fake_get(url, timeout=None, headers=None):
            calls.append(url)
            return self._fake_response(payload)

        ok = refresh_code_index_from_remote(getter=fake_get, cache_path=self.cache_path)

        self.assertTrue(ok)
        self.assertIn("raw.githubusercontent.com", calls[0])
        with open(self.cache_path, "r", encoding="utf-8") as file:
            saved = json.load(file)
        self.assertEqual(saved["codes"]["sh600000"]["name"], "浦发银行")
        self.assertFalse(os.path.exists(self.cache_path + ".tmp"))

    def test_refresh_skips_when_updated_today(self):
        today_text = date.today().strftime("%Y-%m-%d")
        self._write_cache({"sh600000": {"name": "浦发银行"}}, f"{today_text} 15:30:00")

        def fail_get(*args, **kwargs):
            raise AssertionError("当天已更新，不应发起网络请求")

        ok = refresh_code_index_from_remote(getter=fail_get, cache_path=self.cache_path)

        self.assertFalse(ok)

    def test_refresh_runs_again_when_cache_is_stale(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        self._write_cache({"sh600000": {"name": "浦发银行"}}, f"{yesterday} 15:30:00")
        payload = {"codes": {"sz000001": {"name": "平安银行"}}, "updated_at": "today"}

        ok = refresh_code_index_from_remote(
            getter=lambda *a, **k: self._fake_response(payload), cache_path=self.cache_path
        )

        self.assertTrue(ok)
        with open(self.cache_path, "r", encoding="utf-8") as file:
            saved = json.load(file)
        self.assertIn("sz000001", saved["codes"])

    def test_refresh_rejects_bad_payload(self):
        bad_payloads = [
            {},
            {"codes": {}},
            {"codes": []},
            {"other": 1},
        ]
        for payload in bad_payloads:
            ok = refresh_code_index_from_remote(
                getter=lambda *a, **k: self._fake_response(payload), cache_path=self.cache_path
            )
            self.assertFalse(ok)
        self.assertFalse(os.path.exists(self.cache_path))

    def test_refresh_returns_false_on_http_error(self):
        def fake_get(url, timeout=None, headers=None):
            return self._fake_response({}, status_code=404)

        ok = refresh_code_index_from_remote(getter=fake_get, cache_path=self.cache_path)

        self.assertFalse(ok)

    def test_refresh_returns_false_on_network_error(self):
        def fake_get(url, timeout=None, headers=None):
            raise RuntimeError("network down")

        ok = refresh_code_index_from_remote(getter=fake_get, cache_path=self.cache_path)

        self.assertFalse(ok)

    def test_load_index_prefers_downloaded_cache_over_bundled(self):
        cache_dir = os.path.join(self.tmp_dir.name, "StockWidget")
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "stock_codes_list.json"), "w", encoding="utf-8") as file:
            json.dump(
                {
                    "codes": {"sh999999": {"code": "sh999999", "market": "sh", "name": "缓存优先股"}},
                    "updated_at": "2026-08-19 15:30:00",
                },
                file,
                ensure_ascii=False,
            )
        StockCodeSearch = __import__("StockCodeSearch")
        original = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tmp_dir.name
        StockCodeSearch._INDEX_CACHE.pop("default", None)
        try:
            index = load_stock_code_index()
        finally:
            if original is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = original
            StockCodeSearch._INDEX_CACHE.pop("default", None)

        self.assertEqual(index.get("sh999999", {}).get("name"), "缓存优先股")

    def test_refresh_invalidates_memory_cache(self):
        payload = {
            "codes": {"sh600000": {"code": "sh600000", "market": "sh", "name": "浦发银行"}},
            "updated_at": "2026-08-19 15:30:00",
        }
        StockCodeSearch = __import__("StockCodeSearch")
        StockCodeSearch._INDEX_CACHE.pop("default", None)
        self.addCleanup(StockCodeSearch._INDEX_CACHE.pop, "default", None)

        ok = refresh_code_index_from_remote(
            getter=lambda *a, **k: self._fake_response(payload), cache_path=self.cache_path
        )

        self.assertTrue(ok)
        self.assertNotIn("default", StockCodeSearch._INDEX_CACHE)


if __name__ == "__main__":
    unittest.main()
