import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt

from SettingPanel import SettingsDialog


class FakeWindow:
    def __init__(self):
        self.groups = [{"name": "默认", "codes": ["sh000001"]}]
        self.codes = ["sh000001"]
        self.checked_codes = ["sh000001"]
        self.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线"]
        self.refresh_seconds = 2
        self.short_code = False
        self.name_length = 0
        self.b1s1_visible = False
        self.b1s1_display = "qty"
        self.header_visible = False
        self.grid_visible = False
        self.default_color = False
        self.line_extra_px = 1
        self.bg = type("Color", (), {"alpha": lambda self: 191})()
        self.fg = None
        self.hotkey = "Ctrl+Alt+F"
        self.start_on_boot = False
        self.alert_rules = []
        self.price_alerts = []
        self.warning_visible = False
        self.warning_text = ""
        self.market_amount_visible = False
        self.code_names = {"sh000001": "上证指数"}
        self.lookup_names = {}
        self.data_source = {"mode": "sina", "url_template": "", "headers": {}, "fields": {}}
        self.font = type("Font", (), {"family": lambda self: "Microsoft YaHei", "pointSize": lambda self: 10})()

    def header_is_visible(self, header):
        return header in ("名称", "现价", "涨跌幅")

    def windowOpacity(self):
        return 0.9

    def set_groups(self, groups):
        self.groups = groups
        self.codes = [code for group in groups for code in group.get("codes", [])]

    def set_checked_codes(self, codes):
        self.checked_codes = codes

    def set_alert_rules(self, rules):
        self.alert_rules = rules

    def set_price_alerts(self, alerts):
        self.price_alerts = alerts

    def set_data_source(self, data_source):
        self.data_source = data_source

    def set_market_amount_visible(self, visible):
        self.market_amount_visible = visible

    def lookup_code_names(self, codes):
        for code in codes:
            if code in self.lookup_names:
                self.code_names[code] = self.lookup_names[code]
        return {code: self.code_names.get(code, "") for code in codes}

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_add_code_keeps_new_editable_item_in_existing_group(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        group = dlg.tree_codes.topLevelItem(0)

        dlg.tree_codes.setCurrentItem(group)
        dlg._add_code()

        self.assertEqual(group.childCount(), 2)
        self.assertEqual(group.child(1).data(0, dlg._pending_role()), True)
        dlg.close()

    def test_add_code_keeps_new_editable_item_in_new_group(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg._add_group()
        group = dlg.tree_codes.currentItem()
        dlg._add_code()

        self.assertEqual(group.childCount(), 1)
        self.assertEqual(group.child(0).data(0, dlg._pending_role()), True)
        dlg.close()

    def test_pending_code_saves_after_user_enters_valid_code(self):
        win = FakeWindow()
        win.code_names["sh512000"] = "券商ETF"
        dlg = SettingsDialog(win, None)
        group = dlg.tree_codes.topLevelItem(0)

        dlg.tree_codes.setCurrentItem(group)
        dlg._add_code()
        item = group.child(1)
        item.setText(0, "512000")
        dlg._on_codes_changed(item)

        self.assertEqual(group.child(1).text(0), "sh512000  券商")
        self.assertEqual(group.child(1).data(0, dlg._pending_role()), False)
        self.assertIn("sh512000", win.codes)
        dlg.close()

    def test_code_tree_displays_cached_two_character_name(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        group = dlg.tree_codes.topLevelItem(0)

        self.assertEqual(group.child(0).text(0), "sh000001  上证")
        self.assertEqual(group.child(0).data(0, Qt.UserRole + 1), "sh000001")
        dlg.close()

    def test_code_tree_looks_up_missing_names_when_opened(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh000001", "sh512000"]}]
        win.codes = ["sh000001", "sh512000"]
        win.checked_codes = ["sh000001", "sh512000"]
        win.lookup_names = {"sh512000": "券商ETF"}

        dlg = SettingsDialog(win, None)
        group = dlg.tree_codes.topLevelItem(0)

        self.assertEqual(group.child(1).text(0), "sh512000  券商")
        dlg.close()

    def test_code_tree_collects_code_from_display_text(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        group = dlg.tree_codes.topLevelItem(0)
        group.child(0).setText(0, "sh000001  上证")

        groups, checked_codes = dlg._collect_groups_from_tree()

        self.assertEqual(groups, [{"name": "默认", "codes": ["sh000001"]}])
        self.assertEqual(checked_codes, ["sh000001"])
        dlg.close()

    def test_alert_targets_can_be_added_edited_and_deleted(self):
        win = FakeWindow()
        win.alert_rules = [{
            "enabled": True,
            "name": "测试提醒",
            "display_mode": "always",
            "targets": [{"code": "sh000001", "op": ">", "pct": 0.0, "volume": False}],
            "message": "测试",
        }]
        dlg = SettingsDialog(win, None)

        self.assertEqual(dlg.list_alert_targets.count(), 1)
        dlg._add_alert_target()
        self.assertEqual(dlg.list_alert_targets.count(), 2)

        dlg.edit_target_code.setText("512000")
        dlg.cmb_target_op.setCurrentIndex(dlg.cmb_target_op.findData(">="))
        dlg.spin_target_pct.setValue(2.0)
        dlg.chk_target_volume.setChecked(True)
        dlg._on_alert_target_editor_changed()

        targets = win.alert_rules[0]["targets"]
        self.assertIn({"code": "sh512000", "op": ">=", "pct": 2.0, "volume": True}, targets)

        dlg._del_alert_target()
        self.assertEqual(dlg.list_alert_targets.count(), 1)
        self.assertEqual(len(win.alert_rules[0]["targets"]), 1)
        dlg.close()

    def test_alert_target_buttons_are_anchored_beside_target_list(self):
        win = FakeWindow()
        win.alert_rules = [{
            "enabled": True,
            "name": "测试提醒",
            "display_mode": "always",
            "targets": [{"code": "sh000001", "op": ">", "pct": 0.0, "volume": False}],
            "message": "测试",
        }]
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(3)
        dlg.show()
        self.app.processEvents()

        target_rect = dlg.list_alert_targets.rect().translated(dlg.list_alert_targets.mapToGlobal(QPoint(0, 0)))
        add_rect = dlg.btn_target_add.rect().translated(dlg.btn_target_add.mapToGlobal(QPoint(0, 0)))
        del_rect = dlg.btn_target_del.rect().translated(dlg.btn_target_del.mapToGlobal(QPoint(0, 0)))

        self.assertGreaterEqual(add_rect.left(), target_rect.right())
        self.assertGreaterEqual(del_rect.left(), target_rect.right())
        self.assertFalse(target_rect.intersects(add_rect))
        self.assertFalse(target_rect.intersects(del_rect))
        dlg.close()

    def test_price_alerts_can_be_added_edited_and_deleted(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg._add_price_alert()
        self.assertEqual(dlg.list_price_alerts.count(), 1)

        dlg.edit_price_alert_code.setText("512000")
        dlg.cmb_price_alert_direction.setCurrentIndex(dlg.cmb_price_alert_direction.findData("below"))
        dlg.spin_price_alert_price.setValue(1.234)
        dlg.edit_price_alert_message.setText("跌破提醒")
        dlg._on_price_alert_editor_changed()

        self.assertEqual(win.price_alerts[0]["code"], "sh512000")
        self.assertEqual(win.price_alerts[0]["direction"], "below")
        self.assertEqual(win.price_alerts[0]["price"], 1.234)
        self.assertEqual(win.price_alerts[0]["message"], "跌破提醒")

        dlg._del_price_alert()
        self.assertEqual(win.price_alerts, [])
        dlg.close()

    def test_data_source_editor_updates_custom_http_config(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg.cmb_data_source_mode.setCurrentIndex(dlg.cmb_data_source_mode.findData("custom"))
        dlg.edit_data_url.setText("https://example.test/quote?codes={codes}")
        dlg.edit_data_headers.setText('{"Authorization":"Bearer demo"}')
        dlg._on_data_source_changed()

        self.assertEqual(win.data_source["mode"], "custom")
        self.assertEqual(win.data_source["url_template"], "https://example.test/quote?codes={codes}")
        self.assertEqual(win.data_source["headers"]["Authorization"], "Bearer demo")
        self.assertTrue(dlg.edit_data_url.isEnabled())
        dlg.close()

    def test_market_amount_checkbox_updates_window(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg.chk_market_amount_visible.setChecked(True)
        dlg._on_market_amount_changed()

        self.assertTrue(win.market_amount_visible)
        dlg.close()


if __name__ == "__main__":
    unittest.main()
