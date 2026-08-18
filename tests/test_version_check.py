import unittest

from VersionCheck import (
    APP_VERSION,
    UpdateChecker,
    _parse_version,
    fetch_latest_release,
    is_newer_version,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeGetter:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error
        self.called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        if self._error:
            raise self._error
        return _FakeResponse(self._payload)


class VersionCheckTests(unittest.TestCase):
    def test_parse_version_basic(self):
        self.assertEqual(_parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(_parse_version("1.0"), (1, 0, 0))
        self.assertEqual(_parse_version("2"), (2, 0, 0))
        self.assertEqual(_parse_version("release-0.9.5-beta"), (0, 9, 5))
        self.assertIsNone(_parse_version(""))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("v1.1.0", current="1.0.0"))
        self.assertTrue(is_newer_version("v1.0.1", current="1.0.0"))
        self.assertFalse(is_newer_version("v1.0.0", current="1.0.0"))
        self.assertFalse(is_newer_version("v0.9.9", current="1.0.0"))
        self.assertFalse(is_newer_version("", current="1.0.0"))

    def test_fetch_latest_release_parses_payload(self):
        getter = _FakeGetter({
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/userSywang/StockWidget/releases/tag/v1.2.3",
            "published_at": "2026-08-01T00:00:00Z",
        })

        result = fetch_latest_release(getter)

        self.assertTrue(getter.called)
        self.assertEqual(result["tag"], "v1.2.3")
        self.assertIn("releases/tag/v1.2.3", result["url"])

    def test_fetch_latest_release_returns_none_on_error(self):
        getter = _FakeGetter(error=RuntimeError("network down"))
        self.assertIsNone(fetch_latest_release(getter))

    def test_fetch_latest_release_returns_none_on_bad_payload(self):
        getter = _FakeGetter({"message": "Not Found"})
        self.assertIsNone(fetch_latest_release(getter))

    def test_update_checker_check_sync(self):
        getter = _FakeGetter({"tag_name": "v9.9.9", "html_url": "", "published_at": ""})
        checker = UpdateChecker(getter=getter)

        result = checker.check_sync()

        self.assertEqual(result["tag"], "v9.9.9")

    def test_update_checker_check_async_invokes_callback(self):
        results = []

        def on_result(result):
            results.append(result)

        getter = _FakeGetter({"tag_name": "v9.9.9", "html_url": "", "published_at": ""})
        checker = UpdateChecker(getter=getter, on_result=on_result)
        import threading
        import time

        started = checker.check_async()
        self.assertTrue(started)
        deadline = time.time() + 3.0
        while not results and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tag"], "v9.9.9")


if __name__ == "__main__":
    unittest.main()
