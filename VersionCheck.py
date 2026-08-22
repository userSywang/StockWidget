# -*- coding: utf-8 -*-
"""版本号常量与更新检测。

数据源：仓库 {BRANCH} 分支根目录的 Version 文件（单行 vX.Y.Z）。
下载源：GitHub Release 附件 {repo}/releases/download/{tag}/StockWidget.exe。
发新版本：改 Version 文件 + 在对应 Release 上传 StockWidget.exe 附件。
"""
import os
import re
import subprocess
import sys
import tempfile
import threading

import requests

try:
    from PySide6.QtCore import QObject, Signal
except Exception:  # 无 Qt 环境（纯逻辑测试）时退化为直接回调
    QObject = None
    Signal = None

if QObject is not None:

    class _UpdateBridge(QObject):
        result_ready = Signal(object)
else:

    class _UpdateBridge:
        pass

APP_VERSION = "1.0.1"
APP_VERSION_TAG = f"v{APP_VERSION}"
REPO = os.environ.get("STOCKWIDGET_UPDATE_REPO", "userSywang/StockWidget")
BRANCH = os.environ.get("STOCKWIDGET_UPDATE_BRANCH", "codex/strategy-alerts-page")
RELEASES_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Version"
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
    """读取 raw 文件 Version，文件内容形如 v1.0.1（单行）。返回 {tag, url} 或 None。"""
    getter = getter or requests.get
    try:
        response = getter(url, timeout=timeout, headers={"User-Agent": _USER_AGENT})
    except Exception:
        return None
    if response.status_code != 200:
        return None
    text = (response.text or "").strip()
    if not text:
        return None
    # 解析首行非空内容作为 tag
    tag = text.splitlines()[0].strip()
    if not tag:
        return None
    return {
        "tag": tag,
        "url": f"https://github.com/{REPO}/releases",
        "published_at": "",
    }


def asset_url_for(tag):
    """指定 tag 对应的 Release 附件下载地址。"""
    return f"https://github.com/{REPO}/releases/download/{tag}/StockWidget.exe"


def download_release_asset(tag, dest_path, getter=None, on_progress=None, timeout=10):
    """后台下载新版本 exe 到 dest_path。

    on_progress(done_bytes, total_bytes) 在数据块到达时回调（total 可能为 0）。
    返回 (ok, error)：ok=True 表示文件写盘完成。
    """
    getter = getter or requests.get
    try:
        response = getter(
            asset_url_for(tag),
            stream=True,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
    except Exception as exc:
        return False, f"无法连接下载服务器：{exc}"
    try:
        if response.status_code != 200:
            return False, f"下载失败（HTTP {response.status_code}）：请确认 Release 已上传 StockWidget.exe 附件"
        total = 0
        try:
            total = int(response.headers.get("Content-Length") or 0)
        except Exception:
            total = 0
        done = 0
        with open(dest_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                if callable(on_progress):
                    try:
                        on_progress(done, total)
                    except Exception:
                        pass
        if done == 0:
            return False, "下载失败：文件内容为空"
        return True, None
    finally:
        try:
            response.close()
        except Exception:
            pass


def new_exe_download_path(tag):
    """新版本 exe 的临时存放路径（按 tag 区分，避免覆盖）。"""
    safe = re.sub(r"[^0-9A-Za-z.\-]", "_", str(tag or "new"))
    return os.path.join(tempfile.gettempdir(), f"StockWidget_update_{safe}.exe")


def build_updater_script(current_exe, new_exe):
    """生成替换脚本内容：等待旧进程退出 -> 覆盖 exe -> 重启 -> 自删。

    启动新 exe 前必须清空 PyInstaller 的解压目录环境变量：脚本由旧进程派生，
    会继承这些变量；新 exe 一旦读到就会跳过解压、直接去旧进程已删除的
    临时目录加载运行时，触发 "Failed to load Python DLL"。
    """
    return (
        "@echo off\r\n"
        ":waitloop\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        '2>nul del "{cur}"\r\n'
        'if exist "{cur}" goto waitloop\r\n'
        'move /y "{new}" "{cur}"\r\n'
        'set "_MEIPASS2="\r\n'
        'set "_PYI_APPLICATION_HOME_DIR="\r\n'
        'set "_PYI_ARCHIVE_FILE="\r\n'
        'set "_PYI_PARENT_PROCESS_LEVEL="\r\n'
        'start "" "{cur}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    ).format(cur=current_exe, new=new_exe)


def apply_update_and_restart(new_exe_path):
    """写替换脚本并拉起执行；成功返回 True（调用方随后应退出程序）。

    仅在打包后的 exe（sys.frozen）下生效；脚本模式下返回 False。
    """
    if not getattr(sys, "frozen", False):
        return False
    current_exe = os.path.abspath(sys.executable)
    new_exe = os.path.abspath(new_exe_path)
    if not os.path.isfile(new_exe):
        return False
    bat_path = os.path.join(os.path.dirname(current_exe), "StockWidget_updater.bat")
    try:
        with open(bat_path, "w", encoding="mbcs", newline="") as fh:
            fh.write(build_updater_script(current_exe, new_exe))
    except Exception:
        return False
    try:
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except Exception:
        try:
            os.remove(bat_path)
        except Exception:
            pass
        return False
    return True


class UpdateChecker:
    """版本更新检查器：支持同步检查与后台线程检查（不阻塞 UI）。"""

    def __init__(self, getter=None, on_result=None, repo=REPO, branch=BRANCH, timeout=5):
        self._getter = getter
        self._on_result = on_result
        self._url = f"https://raw.githubusercontent.com/{repo}/{branch}/Version"
        self._timeout = timeout
        self._lock = threading.Lock()
        self._running = False
        self._bridge = None

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
        self._ensure_bridge()
        self._running = True

        def _run():
            try:
                result = self.check_sync()
            finally:
                self._running = False
            self._deliver(result)

        threading.Thread(target=_run, daemon=True).start()
        return True

    def _ensure_bridge(self):
        # 工作线程没有 Qt 事件循环，直接回调里再操作 UI/QTimer 会失效；
        # 有 QApplication 时用信号把结果排队送回主线程，没有则退化为直接回调（纯逻辑测试）。
        if self._bridge is not None:
            return
        try:
            from PySide6.QtWidgets import QApplication

            if QApplication.instance() is not None:
                bridge = _UpdateBridge()
                bridge.result_ready.connect(self._on_bridge_result)
                self._bridge = bridge
        except Exception:
            self._bridge = None

    def _on_bridge_result(self, result):
        self._emit_callback(result)

    def _deliver(self, result):
        if self._bridge is not None:
            self._bridge.result_ready.emit(result)
        else:
            self._emit_callback(result)

    def _emit_callback(self, result):
        callback = self._on_result
        if callable(callback):
            try:
                callback(result)
            except Exception:
                pass
