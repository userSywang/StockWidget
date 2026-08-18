# -*- coding: utf-8 -*-
"""版本号常量与更新检测。

数据源：GitHub Releases API（https://api.github.com/repos/{repo}/releases/latest）。
发布新版本时：在 GitHub 打 vX.Y.Z tag（CI 已支持 tags v* 自动构建）。
"""
import re
import threading

import requests

APP_VERSION = "1.0.0"
APP_VERSION_TAG = f"v{APP_VERSION}"
REPO = "userSywang/StockWidget"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_USER_AGENT = "StockWidget"


def _parse_version(text):
    """从 tag/版本文本解析出 (major, minor, patch) 数字元组；失败返回 None。"""
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text or ""))
    if not match:
        return None
    return tuple(int(part) if part else 0 for part in match.groups())


def is_newer_version(tag, current=APP_VERSION):
    """远端 tag 版本是否高于当前版本。"""
    latest = _parse_version(tag)
    cur = _parse_version(current)
    if latest is None or cur is None:
        return False
    return latest > cur


def fetch_latest_release(getter=None, url=RELEASES_URL, timeout=5):
    """请求 GitHub Releases API，返回 {tag, url, published_at}；失败返回 None。"""
    getter = getter or requests.get
    try:
        response = getter(url, timeout=timeout, headers={"User-Agent": _USER_AGENT})
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
    if not tag:
        return None
    return {
        "tag": tag,
        "url": str(payload.get("html_url") or "").strip(),
        "published_at": str(payload.get("published_at") or "").strip(),
    }


class UpdateChecker:
    """版本更新检查器：支持同步检查与后台线程检查（不阻塞 UI）。"""

    def __init__(self, getter=None, on_result=None, repo=REPO, timeout=5):
        self._getter = getter
        self._on_result = on_result
        self._url = f"https://api.github.com/repos/{repo}/releases/latest"
        self._timeout = timeout
        self._lock = threading.Lock()
        self._running = False

    @property
    def running(self):
        return self._running

    def check_sync(self):
        """同步检查，返回 {tag, url, published_at} 或 None。"""
        return fetch_latest_release(self._getter, self._url, self._timeout)

    def check_async(self):
        """后台线程检查，完成后回调 on_result(result)；已有检查进行中时直接返回。"""
        if self._running:
            return False
        self._running = True

        def _run():
            try:
                result = self.check_sync()
            finally:
                self._running = False
            callback = self._on_result
            if callable(callback):
                try:
                    callback(result)
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()
        return True
