import unittest

from HotkeyManager import MOD_ALT, MOD_CONTROL, HotkeyResult, GlobalHotkeyManager, normalize_hotkey, parse_hotkey


class HotkeyManagerTests(unittest.TestCase):
    def test_normalize_hotkey_maps_numpad_dot(self):
        self.assertEqual(normalize_hotkey("."), "decimal")
        self.assertEqual(normalize_hotkey("小键盘."), "decimal")

    def test_parse_hotkey_supports_numpad_decimal_without_modifier(self):
        parsed = parse_hotkey("decimal")

        self.assertEqual(parsed, (0, 0x6E, "decimal"))

    def test_parse_hotkey_supports_modifier_combinations(self):
        parsed = parse_hotkey("Ctrl+Alt+F")

        self.assertEqual(parsed, (MOD_CONTROL | MOD_ALT, ord("F"), "Ctrl+Alt+F"))

    def test_dispatch_calls_registered_callback(self):
        manager = GlobalHotkeyManager()
        calls = []
        manager._callbacks[7] = lambda: calls.append("called")

        self.assertTrue(manager.dispatch(7))
        self.assertEqual(calls, ["called"])
        self.assertFalse(manager.dispatch(8))

    def test_hotkey_result_bool_uses_ok(self):
        self.assertTrue(HotkeyResult(True, handle=1))
        self.assertFalse(HotkeyResult(False, reason="failed"))


if __name__ == "__main__":
    unittest.main()
