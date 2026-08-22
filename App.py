import sys, os, winreg

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle, QMessageBox
from WidgetPanel import FloatLabel
from SettingPanel import SettingsDialog
from ConfigStore import load_config, save_config
from VersionCheck import (
    APP_VERSION_TAG,
    UpdateChecker,
    apply_update_and_restart,
    download_release_asset,
    is_newer_version,
    new_exe_download_path,
)

# ----- 程序与资源 -----
APP_NAME = "StockWidget"
APP_ICON_FILE = "StockWidget.ico"

def resource_path(rel_path):
    base = getattr(sys, "_MEIPASS", "")
    return os.path.join(base, rel_path)

class App(QApplication):
    update_download_progress = Signal(int, int)
    update_download_finished = Signal(object)
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)
        icon_path = resource_path(APP_ICON_FILE)
        # load saved icon choice from config
        cfg = load_config()
        icon_choice = cfg.get('app_icon')
        self._app_icon_choice = icon_choice
        def _resolve_icon(choice):
            # choice can be None, 'default', 'std:NAME' or a file path
            if not choice or choice == 'default':
                p = resource_path(APP_ICON_FILE)
                if os.path.exists(p):
                    return QIcon(p)
                return self.style().standardIcon(QStyle.SP_ComputerIcon)
            if isinstance(choice, str) and choice.startswith('std:'):
                key = choice.split(':',1)[1]
                mapping = {
                    'computer': QStyle.SP_ComputerIcon,
                    'network': QStyle.SP_DriveNetIcon,
                    'folder': QStyle.SP_DirIcon,
                    'file': QStyle.SP_FileIcon,
                    'trash': QStyle.SP_TrashIcon,
                    'desktop': QStyle.SP_DesktopIcon,
                }
                sp = mapping.get(key, QStyle.SP_ComputerIcon)
                return self.style().standardIcon(sp)
            # assume it's a file path
            try:
                if os.path.exists(choice):
                    return QIcon(choice)
            except Exception:
                pass
            return self.style().standardIcon(QStyle.SP_ComputerIcon)

        app_icon = _resolve_icon(icon_choice)
        self.setWindowIcon(app_icon)

        cfg = load_config()
        self.win = FloatLabel(cfg)
        # Apply start-on-boot setting from config
        try:
            self.set_start_on_boot(bool(cfg.get("start_on_boot", False)))
        except Exception:
            pass
        self.win.set_on_change(self.save_now)
        self.win.set_open_settings_callback(self.open_settings)

        self.tray = QSystemTrayIcon(app_icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction(QAction("显示/隐藏 浮窗", self, triggered=self.toggle_win))
        menu.addAction(QAction("设置…", self, triggered=self.open_settings))
        menu.addSeparator()
        menu.addAction(QAction("退出", self, triggered=self.quit_app))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        self.settings_dlg = None
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()
        self.win.setFocus(Qt.ActiveWindowFocusReason)

        # 版本更新检测
        self._update_checker = UpdateChecker(on_result=self._on_update_check_result)
        self._update_downloading = False
        self.update_download_progress.connect(self._on_update_download_progress)
        self.update_download_finished.connect(self._on_update_download_finished)
        self._check_updates_on_startup = bool(cfg.get("check_updates_on_startup", True))
        if self._check_updates_on_startup:
            QTimer.singleShot(2000, self._check_updates_on_startup_delayed)

        # 代码索引后台刷新（每日一次；远端文件由 update-codes 工作流自动维护）
        QTimer.singleShot(5000, self._refresh_code_index_async)

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick): self.toggle_win()

    def toggle_win(self):
        if self.win.isVisible():
            self.win.hide()
        else:
            self.win.show()
            self.win.raise_()
            self.win.activateWindow()
            self.win.setFocus(Qt.ActiveWindowFocusReason)
        self.save_now()

    def open_settings(self):
        if self.settings_dlg and self.settings_dlg.isVisible():
            self.settings_dlg.raise_()
            self.settings_dlg.activateWindow()
            return
        self.settings_dlg = SettingsDialog(self.win, self.win, app=self)
        # 将设置窗口放在屏幕正中
        screen = QApplication.primaryScreen().availableGeometry()
        self.settings_dlg.adjustSize()
        cx = screen.left() + (screen.width() - self.settings_dlg.width()) // 2
        cy = screen.top() + (screen.height() - self.settings_dlg.height()) // 2
        self.settings_dlg.move(QPoint(cx, cy))
        self.settings_dlg.show()
        self.settings_dlg.raise_()
        self.settings_dlg.activateWindow()

    def quit_app(self):
        self.tray.hide()
        self.save_now()
        try:
            self.win.shutdown_background()
        except Exception:
            pass
        sys.exit(0)

    def save_now(self):
        cfg = self.win.current_config()
        # persist selected app icon
        try:
            cfg['app_icon'] = getattr(self, '_app_icon_choice', None)
        except Exception:
            pass
        # persist update-check preference
        try:
            cfg['check_updates_on_startup'] = bool(getattr(self, '_check_updates_on_startup', True))
        except Exception:
            pass
        save_config(cfg)

    # ---- 版本更新检测 ----

    def _check_updates_on_startup_delayed(self):
        if not getattr(self, "_check_updates_on_startup", True):
            return
        try:
            self._update_checker.check_async()
        except Exception:
            pass

    def _refresh_code_index_async(self):
        import threading
        from StockCodeSearch import refresh_code_index_from_remote

        threading.Thread(target=refresh_code_index_from_remote, daemon=True).start()

    def _on_update_check_result(self, result):
        # worker 线程回调，转回主线程弹窗
        QTimer.singleShot(0, lambda: self._show_update_prompt(result))

    def _show_update_prompt(self, result):
        if not result or not is_newer_version(result.get("tag", "")):
            return
        if self._update_downloading:
            return
        tag = result.get("tag", "")
        box = QMessageBox(self.win)
        box.setWindowTitle("发现新版本")
        box.setText(f"StockWidget 有新版本 {tag}（当前 {APP_VERSION_TAG}）")
        box.setInformativeText("是否后台下载并自动更新？（下载不阻塞看盘，完成后询问重启）")
        update = box.addButton("后台下载并更新", QMessageBox.AcceptRole)
        box.addButton("稍后再说", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is update:
            self._start_update_download(tag)

    # ---- 后台下载与自动更新 ----

    def _start_update_download(self, tag):
        """后台线程下载新版本 exe，进度/完成经信号回主线程。"""
        if getattr(self, "_update_downloading", False):
            return
        self._update_downloading = True
        self._set_update_status_text(f"正在后台下载新版本 {tag}…")
        dest = new_exe_download_path(tag)
        self._update_download_tag = tag
        self._update_download_dest = dest

        def _worker():
            ok, error = download_release_asset(
                tag, dest, on_progress=self._emit_update_download_progress
            )
            self.update_download_finished.emit({"ok": ok, "error": error, "tag": tag})

        import threading

        threading.Thread(target=_worker, daemon=True).start()

    def _emit_update_download_progress(self, done, total):
        self.update_download_progress.emit(done, total)

    def _on_update_download_progress(self, done, total):
        mb = done / 1024.0 / 1024.0
        if total > 0:
            pct = int(done * 100 / total)
            text = f"正在下载新版本… {pct}%（{mb:.1f} MB）"
        else:
            text = f"正在下载新版本… 已下载 {mb:.1f} MB"
        self._set_update_status_text(text)

    def _on_update_download_finished(self, result):
        self._update_downloading = False
        ok = bool(result.get("ok"))
        tag = result.get("tag", "")
        if not ok:
            self._set_update_status_text(f"下载失败：{result.get('error', '未知错误')}")
            QMessageBox.warning(self.win, "更新下载失败", f"新版本下载失败：\n{result.get('error', '未知错误')}")
            return
        self._set_update_status_text(f"新版本 {tag} 下载完成，重启后生效。")
        box = QMessageBox(self.win)
        box.setWindowTitle("更新就绪")
        box.setText(f"新版本 {tag} 已下载完成")
        box.setInformativeText("是否立即重启 StockWidget 完成更新？")
        now = box.addButton("立即重启更新", QMessageBox.AcceptRole)
        box.addButton("稍后（下次退出时手动替换）", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self._apply_update_now()

    def _apply_update_now(self):
        dest = getattr(self, "_update_download_dest", "")
        if not apply_update_and_restart(dest):
            QMessageBox.warning(
                self.win,
                "更新失败",
                "无法自动替换程序（可能是脚本模式运行或文件被占用）。\n"
                f"新版本已下载到：\n{dest}",
            )
            return
        self.quit_app()

    def _set_update_status_text(self, text):
        dlg = getattr(self, "settings_dlg", None)
        if dlg is not None and dlg.isVisible():
            try:
                dlg.set_update_status_text(text)
            except Exception:
                pass

    def check_updates_manual(self, extra_callback=None):
        """设置面板手动检查更新（异步，完成后弹窗提示结果）。"""
        def _on_result(result):
            self._on_manual_update_check_result(result)
            if callable(extra_callback):
                try:
                    extra_callback(result)
                except Exception:
                    pass
        checker = UpdateChecker(on_result=_on_result)
        self._manual_update_checker = checker
        return checker.check_async()

    def _on_manual_update_check_result(self, result):
        QTimer.singleShot(0, lambda: self._show_manual_check_result(result))

    def _show_manual_check_result(self, result):
        if isinstance(result, dict) and result.get("rate_limited"):
            QMessageBox.information(None, "检查更新", "请求过于频繁被服务器限流，请 1 小时后再试。")
            return
        if not result:
            QMessageBox.information(None, "检查更新", "检查失败：无法连接版本服务器，请检查网络后稍后重试。")
            return
        if is_newer_version(result.get("tag", "")):
            self._show_update_prompt(result)
            return
        QMessageBox.information(None, "检查更新", f"当前已是最新版本（{APP_VERSION_TAG}）。")

    def set_check_updates_on_startup(self, enabled: bool):
        self._check_updates_on_startup = bool(enabled)
        try:
            self.save_now()
        except Exception:
            pass

    def set_app_icon(self, choice):
        """Set application and tray icon. `choice` can be None/'default', 'std:KEY' or a file path."""
        self._app_icon_choice = choice
        # resolve to QIcon
        def _resolve_icon(choice):
            if not choice or choice == 'default':
                p = resource_path(APP_ICON_FILE)
                if os.path.exists(p):
                    return QIcon(p)
                return self.style().standardIcon(QStyle.SP_ComputerIcon)
            if isinstance(choice, str) and choice.startswith('std:'):
                key = choice.split(':',1)[1]
                mapping = {
                    'computer': QStyle.SP_ComputerIcon,
                    'network': QStyle.SP_DriveNetIcon,
                    'folder': QStyle.SP_DirIcon,
                    'file': QStyle.SP_FileIcon,
                    'trash': QStyle.SP_TrashIcon,
                    'desktop': QStyle.SP_DesktopIcon,
                }
                sp = mapping.get(key, QStyle.SP_ComputerIcon)
                return self.style().standardIcon(sp)
            try:
                if os.path.exists(choice):
                    return QIcon(choice)
            except Exception:
                pass
            return self.style().standardIcon(QStyle.SP_ComputerIcon)

        icon = _resolve_icon(choice)
        try:
            self.setWindowIcon(icon)
        except Exception:
            pass
        try:
            if hasattr(self, 'tray') and self.tray is not None:
                self.tray.setIcon(icon)
        except Exception:
            pass

    def set_start_on_boot(self, enabled: bool):
        """Enable or disable Windows startup by writing/removing Run key in HKCU."""
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            name = APP_NAME
            if enabled:
                if getattr(sys, 'frozen', False):
                    cmd = f'"{sys.executable}"'
                else:
                    cmd = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, name)
                except OSError:
                    # value not present
                    pass
        except Exception:
            pass
