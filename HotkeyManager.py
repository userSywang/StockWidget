import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_MAP = {
    "decimal": 0x6E,
    "numpad_decimal": 0x6E,
    ".": 0xBE,
    "period": 0xBE,
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
}
for number in range(10):
    VK_MAP[str(number)] = ord(str(number))
for letter in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[letter] = ord(letter.upper())
for index in range(1, 13):
    VK_MAP[f"f{index}"] = 0x6F + index


def normalize_hotkey(value):
    text = str(value or "").strip()
    if not text:
        return "decimal"
    normalized = text.lower().replace("num.", "decimal").replace("numpad.", "decimal")
    if normalized in (".", "num decimal", "numpad decimal", "小键盘.", "小键盘点"):
        return "decimal"
    return text


def parse_hotkey(value):
    hotkey = normalize_hotkey(value).lower()
    modifiers = 0
    key = ""
    for part in hotkey.split("+"):
        token = part.strip()
        if not token:
            continue
        if token in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif token == "alt":
            modifiers |= MOD_ALT
        elif token == "shift":
            modifiers |= MOD_SHIFT
        elif token in ("win", "meta", "super"):
            modifiers |= MOD_WIN
        else:
            if key:
                return None
            key = token
    vk = VK_MAP.get(key)
    if vk is None:
        return None
    return modifiers, vk, normalize_hotkey(value)


class HotkeyResult:
    def __init__(self, ok, handle=None, reason=""):
        self.ok = bool(ok)
        self.handle = handle
        self.reason = reason

    def __bool__(self):
        return self.ok


class _WindowsHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) != b"windows_generic_MSG":
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.message != WM_HOTKEY:
                return False, 0
            return self.manager.dispatch(int(msg.wParam)), 0
        except Exception:
            return False, 0


class GlobalHotkeyManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._callbacks = {}
        self._next_id = 1
        self._filter = None

    def register(self, hotkey, callback):
        parsed = parse_hotkey(hotkey)
        if parsed is None:
            return HotkeyResult(False, reason="invalid")
        if sys.platform != "win32":
            return HotkeyResult(False, reason="unsupported")
        modifiers, vk, _label = parsed
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            if self._filter is None:
                self._filter = _WindowsHotkeyFilter(self)
                app = QCoreApplication.instance()
                if app is not None:
                    app.installNativeEventFilter(self._filter)
            hotkey_id = self._next_id
            ok = user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk)
            if not ok:
                return HotkeyResult(False, reason="failed")
            self._callbacks[hotkey_id] = callback
            self._next_id += 1
            return HotkeyResult(True, handle=hotkey_id)
        except Exception as exc:
            return HotkeyResult(False, reason=str(exc) or "failed")

    def unregister(self, handle):
        if handle is None or sys.platform != "win32":
            self._callbacks.pop(handle, None)
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.UnregisterHotKey(None, int(handle))
        except Exception:
            pass
        self._callbacks.pop(handle, None)

    def unregister_all(self):
        for handle in list(self._callbacks):
            self.unregister(handle)

    def dispatch(self, handle):
        callback = self._callbacks.get(handle)
        if not callable(callback):
            return False
        callback()
        return True
