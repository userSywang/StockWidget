import os
import tempfile
import threading
import time
import unittest

from VersionCheck import (
    APP_VERSION,
    UpdateChecker,
    _parse_version,
    apply_update_and_restart,
    asset_url_for,
    build_updater_script,
    download_release_asset,
    fetch_latest_release,
    is_newer_version,
    new_exe_download_path,
)


class _FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def json(self):
        return {}


class _FakeGetter:
    def __init__(self, text="", error=None):
        self._text = text
        self._error = error
        self.called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        if self._error:
            raise self._error
        return _FakeResponse(self._text)


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
        getter = _FakeGetter(text="v1.2.3")

        result = fetch_latest_release(getter)

        self.assertTrue(getter.called)
        self.assertEqual(result["tag"], "v1.2.3")
        self.assertIn("/releases", result["url"])

    def test_fetch_latest_release_returns_none_on_error(self):
        getter = _FakeGetter(error=RuntimeError("network down"))
        self.assertIsNone(fetch_latest_release(getter))

    def test_fetch_latest_release_returns_none_on_bad_payload(self):
        getter = _FakeGetter(text="")
        self.assertIsNone(fetch_latest_release(getter))

    def test_update_checker_check_sync(self):
        getter = _FakeGetter(text="v9.9.9")
        checker = UpdateChecker(getter=getter)

        result = checker.check_sync()

        self.assertEqual(result["tag"], "v9.9.9")

    def _wait_for(self, results, timeout=3.0):
        # 若会话中已有 QApplication（其他测试创建），回调经主线程信号投递，需要泵事件
        app = None
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
        except Exception:
            app = None
        deadline = time.time() + timeout
        while not results and time.time() < deadline:
            if app is not None:
                app.processEvents()
            time.sleep(0.02)

    def test_update_checker_check_async_invokes_callback(self):
        results = []

        def on_result(result):
            results.append(result)

        getter = _FakeGetter(text="v9.9.9")
        checker = UpdateChecker(getter=getter, on_result=on_result)

        started = checker.check_async()
        self.assertTrue(started)
        self._wait_for(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tag"], "v9.9.9")

    def test_update_checker_check_async_delivers_on_main_thread_with_qapp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        results = []
        main_thread = threading.get_ident()

        def on_result(result):
            results.append((result, threading.get_ident()))

        getter = _FakeGetter(text="v1.2.3")
        checker = UpdateChecker(getter=getter, on_result=on_result)
        self.assertTrue(checker.check_async())

        deadline = time.time() + 3.0
        while not results and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)
        self.assertEqual(len(results), 1)
        result, thread_id = results[0]
        self.assertEqual(result["tag"], "v1.2.3")
        self.assertEqual(thread_id, main_thread)


class _FakeStreamResponse:
    def __init__(self, chunks, status_code=200, length=None):
        self._chunks = chunks
        self.status_code = status_code
        self.headers = {"Content-Length": str(length if length is not None else sum(len(c) for c in chunks))}
        self.closed = False

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)

    def close(self):
        self.closed = True


class _FakeStreamGetter:
    def __init__(self, response):
        self._response = response
        self.called_with = None

    def __call__(self, url, **kwargs):
        self.called_with = (url, kwargs)
        return self._response


class AssetDownloadTests(unittest.TestCase):
    def test_asset_url_for(self):
        url = asset_url_for("v1.0.1")
        self.assertEqual(url, "https://github.com/userSywang/StockWidget/releases/download/v1.0.1/StockWidget.exe")

    def test_download_release_asset_writes_file_and_progress(self):
        chunks = [b"a" * 100, b"b" * 50]
        getter = _FakeStreamGetter(_FakeStreamResponse(chunks))
        progress = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "new.exe")
            ok, error = download_release_asset("v9.9.9", dest, getter=getter, on_progress=lambda d, t: progress.append((d, t)))
            self.assertTrue(ok)
            self.assertIsNone(error)
            with open(dest, "rb") as fh:
                self.assertEqual(fh.read(), b"a" * 100 + b"b" * 50)
        self.assertEqual(progress, [(100, 150), (150, 150)])
        url = getter.called_with[0]
        self.assertIn("v9.9.9", url)
        self.assertTrue(getter.called_with[1].get("stream"))
        self.assertTrue(getter._response.closed)

    def test_download_release_asset_404_reports_hint(self):
        getter = _FakeStreamGetter(_FakeStreamResponse([], status_code=404))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "new.exe")
            ok, error = download_release_asset("v9.9.9", dest, getter=getter)
        self.assertFalse(ok)
        self.assertIn("StockWidget.exe 附件", error)

    def test_download_release_asset_empty_body(self):
        getter = _FakeStreamGetter(_FakeStreamResponse([b""]))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "new.exe")
            ok, error = download_release_asset("v9.9.9", dest, getter=getter)
        self.assertFalse(ok)
        self.assertIn("为空", error)

    def test_download_release_asset_network_error(self):
        def boom(*args, **kwargs):
            raise ConnectionError("refused")

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "new.exe")
            ok, error = download_release_asset("v9.9.9", dest, getter=boom)
        self.assertFalse(ok)
        self.assertIn("无法连接", error)

    def test_new_exe_download_path_sanitized(self):
        path = new_exe_download_path("v1.2.3/evil")
        self.assertNotIn("/", os.path.basename(path))
        self.assertIn("v1.2.3_evil", path)

    def test_build_updater_script_contains_paths_and_self_delete(self):
        script = build_updater_script(r"F:\app\StockWidget.exe", r"C:\tmp\new.exe")
        self.assertIn('del "F:\\app\\StockWidget.exe"', script)
        self.assertIn('move /y "C:\\tmp\\new.exe" "F:\\app\\StockWidget.exe"', script)
        self.assertIn('start "" "F:\\app\\StockWidget.exe"', script)
        self.assertIn('del "%~f0"', script)
        self.assertIn(":waitloop", script)

    def test_build_updater_script_clears_pyinstaller_env(self):
        # 新 exe 启动前必须清掉继承的解压目录变量，否则指向已删除的旧临时目录
        script = build_updater_script(r"F:\app\StockWidget.exe", r"C:\tmp\new.exe")
        for var in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
            self.assertIn(f'set "{var}="', script)
        # 清理动作必须在 start 之前
        self.assertLess(script.index('set "_MEIPASS2="'), script.index("start"))

    def test_apply_update_and_restart_disabled_in_script_mode(self):
        # 脚本模式（python 直接运行，无 sys.frozen）不应执行任何替换
        self.assertFalse(getattr(__import__("sys"), "frozen", False))
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "new.exe")
            with open(dest, "wb") as fh:
                fh.write(b"x")
            self.assertFalse(apply_update_and_restart(dest))


if __name__ == "__main__":
    unittest.main()
