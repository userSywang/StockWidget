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
        self.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线", "MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"]
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
        self.strategy_alert_config = {}
        self.code_tags = {}
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

    def set_strategy_alert_config(self, config):
        self.strategy_alert_config = config

    def set_code_tags(self, code_tags):
        self.code_tags = code_tags

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

    def test_current_self_selected_code_opens_price_alert_editor(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        dlg = SettingsDialog(win, None)

        code_item = dlg.tree_codes.topLevelItem(0).child(0)
        dlg.tree_codes.setCurrentItem(code_item)
        dlg._open_price_alert_for_current_code()

        self.assertEqual(dlg.tabs.currentIndex(), 3)
        self.assertEqual(win.price_alerts[0]["code"], "sh603259")
        self.assertEqual(dlg.edit_price_alert_code.text(), "sh603259")
        dlg.close()

    def test_current_self_selected_code_opens_strategy_position_editor(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        dlg = SettingsDialog(win, None)

        code_item = dlg.tree_codes.topLevelItem(0).child(0)
        dlg.tree_codes.setCurrentItem(code_item)
        dlg._open_strategy_for_current_code()

        self.assertEqual(dlg.tabs.currentIndex(), 4)
        self.assertEqual(win.strategy_alert_config["positions"][0]["code"], "sh603259")
        self.assertEqual(dlg.edit_strategy_code.text(), "sh603259")
        dlg.close()

    def test_alert_and_strategy_lists_show_stock_short_names(self):
        win = FakeWindow()
        win.code_names = {"sh603259": "药明康德"}
        win.price_alerts = [{"enabled": True, "code": "sh603259", "direction": "below", "price": 145.0, "message": ""}]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 149.448, "strategy_id": "default"}],
        }
        dlg = SettingsDialog(win, None)

        self.assertIn("药明", dlg.list_price_alerts.item(0).text())
        self.assertIn("药明", dlg.list_strategy_positions.item(0).text())
        dlg.close()

    def test_self_selected_code_tags_are_saved_and_displayed(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        win.code_tags = {}
        dlg = SettingsDialog(win, None)

        code_item = dlg.tree_codes.topLevelItem(0).child(0)
        dlg.tree_codes.setCurrentItem(code_item)
        dlg.cmb_code_holding.setCurrentIndex(dlg.cmb_code_holding.findData("hold"))
        dlg.cmb_code_cycle.setCurrentIndex(dlg.cmb_code_cycle.findData("short"))
        dlg.cmb_code_priority.setCurrentIndex(dlg.cmb_code_priority.findData("focus"))
        dlg._on_code_tag_changed()

        self.assertEqual(win.code_tags["sh603259"]["holding"], "hold")
        self.assertEqual(win.code_tags["sh603259"]["cycle"], "short")
        self.assertIn("持有", code_item.text(0))
        self.assertIn("短线", code_item.text(0))
        dlg.close()

    def test_display_data_page_includes_ma_and_strategy_columns(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        labels = {cb.text() for cb in dlg.cbs}

        self.assertTrue({"MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"}.issubset(labels))
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

    def test_strategy_page_edits_positions_and_rules(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg.tabs.setCurrentIndex(4)
        dlg._add_strategy_position()
        self.assertEqual(dlg.list_strategy_positions.count(), 1)

        dlg.edit_strategy_code.setText("512000")
        dlg.spin_strategy_cost.setValue(1.234)
        dlg.edit_strategy_buy_date.setText("2026-08-05")
        dlg.spin_strategy_position_pct.setValue(18.0)
        dlg.edit_strategy_note.setText("测试持仓")
        dlg._on_strategy_position_editor_changed()
        dlg.chk_strategy_enabled.setChecked(True)
        dlg.chk_strategy_notify_desktop.setChecked(True)
        dlg.chk_strategy_notify_panel.setChecked(True)
        dlg.chk_strategy_notify_remote.setChecked(True)
        dlg.cmb_strategy_remote_channel.setCurrentIndex(dlg.cmb_strategy_remote_channel.findData("wecom"))
        dlg.edit_strategy_webhook.setText("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
        dlg.spin_strategy_loss.setValue(6.0)
        dlg.spin_strategy_stale_days.setValue(10)
        dlg._on_strategy_config_changed()

        self.assertTrue(win.strategy_alert_config["enabled"])
        self.assertEqual(win.strategy_alert_config["positions"][0]["code"], "sh512000")
        self.assertEqual(win.strategy_alert_config["positions"][0]["cost_price"], 1.234)
        self.assertEqual(win.strategy_alert_config["positions"][0]["position_pct"], 18.0)
        self.assertEqual(win.strategy_alert_config["positions"][0]["note"], "测试持仓")
        self.assertTrue(win.strategy_alert_config["notifications"]["desktop_popup"])
        self.assertTrue(win.strategy_alert_config["notifications"]["panel_highlight"])
        self.assertTrue(win.strategy_alert_config["notifications"]["remote_push"])
        self.assertEqual(win.strategy_alert_config["notifications"]["remote_channel"], "wecom")
        self.assertEqual(win.strategy_alert_config["notifications"]["webhook_url"], "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
        self.assertEqual(win.strategy_alert_config["positions"][0]["rules"]["max_loss_pct"], 6.0)
        self.assertEqual(win.strategy_alert_config["positions"][0]["rules"]["stale_position_days"], 10)
        preview = [dlg.list_strategy_preview.item(i).text() for i in range(dlg.list_strategy_preview.count())]
        self.assertTrue(any("桌面弹窗" in row and "远程推送" in row for row in preview))
        self.assertTrue(any("浮亏达到 6.0%" in row for row in preview))

        dlg._del_strategy_position()
        self.assertEqual(win.strategy_alert_config["positions"], [])
        dlg.close()

    def test_strategy_rules_follow_selected_position_and_save_to_position(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [
                {"code": "sh512000", "cost_price": 1.0, "rules": {"max_loss_pct": 4.0}},
                {"code": "sh000001", "cost_price": 2.0, "rules": {"max_loss_pct": 8.0}},
            ],
        }
        dlg = SettingsDialog(win, None)
        dlg.list_strategy_positions.setCurrentRow(1)
        self.assertEqual(dlg.spin_strategy_loss.value(), 8.0)

        dlg.spin_strategy_loss.setValue(9.0)
        dlg._save_strategy_position()

        self.assertEqual(win.strategy_alert_config["positions"][1]["rules"]["max_loss_pct"], 9.0)
        self.assertEqual(win.strategy_alert_config["positions"][0]["rules"]["max_loss_pct"], 4.0)
        dlg.close()

    def test_strategy_rule_edits_do_not_change_other_default_positions(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [
                {"code": "sh603259", "cost_price": 100.0, "strategy_id": "default"},
                {"code": "sh600584", "cost_price": 100.0, "strategy_id": "default"},
            ],
        }
        dlg = SettingsDialog(win, None)

        dlg.list_strategy_positions.setCurrentRow(0)
        dlg.spin_strategy_loss.setValue(10.0)
        dlg._save_strategy_position()

        dlg.list_strategy_positions.setCurrentRow(1)
        self.assertEqual(dlg.spin_strategy_loss.value(), 5.0)
        dlg.spin_strategy_loss.setValue(5.0)
        dlg._save_strategy_position()

        positions = {item["code"]: item for item in win.strategy_alert_config["positions"]}
        self.assertEqual(positions["sh603259"]["rules"]["max_loss_pct"], 10.0)
        self.assertEqual(positions["sh600584"]["rules"]["max_loss_pct"], 5.0)
        self.assertEqual(win.strategy_alert_config["rules"]["max_loss_pct"], 5.0)

        dlg.list_strategy_positions.setCurrentRow(0)
        self.assertEqual(dlg.spin_strategy_loss.value(), 10.0)
        dlg.list_strategy_positions.setCurrentRow(1)
        self.assertEqual(dlg.spin_strategy_loss.value(), 5.0)
        dlg.close()

    def test_strategy_rules_are_hidden_until_a_position_is_selected(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh512000", "cost_price": 1.0}],
        }
        dlg = SettingsDialog(win, None)
        self.assertTrue(dlg.strategy_rules_group.isHidden())

        dlg.list_strategy_positions.setCurrentRow(0)
        self.assertFalse(dlg.strategy_rules_group.isHidden())
        self.assertIn("sh512000", dlg.lbl_strategy_scope.text())
        dlg.close()

    def test_strategy_rule_controls_do_not_overlap_after_show(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh512000", "cost_price": 1.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(4)
        dlg.list_strategy_positions.setCurrentRow(0)
        dlg._on_strategy_params_edit()
        dlg.show()
        self.app.processEvents()

        widgets = [dlg.chk_strategy_loss, dlg.chk_strategy_stock_ma5, dlg.chk_strategy_trailing]
        rects = [
            widget.rect().translated(widget.mapToGlobal(widget.rect().topLeft()))
            for widget in widgets
        ]
        for widget, rect in zip(widgets, rects):
            self.assertTrue(widget.isVisible())
            self.assertGreater(rect.width(), 0)
            self.assertGreater(rect.height(), 0)
        for index, rect in enumerate(rects):
            for other in rects[index + 1:]:
                self.assertFalse(rect.intersects(other))
        self.assertGreaterEqual(dlg.size().height(), 660)
        dlg.close()

    def test_strategy_tier_controls_are_compact_and_visible(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 100.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(4)
        dlg.list_strategy_positions.setCurrentRow(0)
        dlg._on_strategy_params_edit()
        dlg.show()
        self.app.processEvents()

        for profit, lock in zip(dlg.spin_strategy_tier_profit, dlg.spin_strategy_tier_lock):
            self.assertLessEqual(profit.width(), 80)
            self.assertLessEqual(lock.width(), 80)
            profit_rect = profit.rect().translated(profit.mapTo(dlg.strategy_config_group, profit.rect().topLeft()))
            lock_rect = lock.rect().translated(lock.mapTo(dlg.strategy_config_group, lock.rect().topLeft()))
            self.assertTrue(dlg.strategy_config_group.rect().contains(profit_rect))
            self.assertTrue(dlg.strategy_config_group.rect().contains(lock_rect))
        dlg.close()

    def test_strategy_notify_webhook_controls_are_visible_and_not_overlapped(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(4)
        dlg.show()
        self.app.processEvents()

        page_rect = dlg.tabs.currentWidget().rect().translated(dlg.tabs.currentWidget().mapToGlobal(QPoint(0, 0)))
        remote_rect = dlg.chk_strategy_notify_remote.rect().translated(dlg.chk_strategy_notify_remote.mapToGlobal(QPoint(0, 0)))
        channel_rect = dlg.cmb_strategy_remote_channel.rect().translated(dlg.cmb_strategy_remote_channel.mapToGlobal(QPoint(0, 0)))
        webhook_rect = dlg.edit_strategy_webhook.rect().translated(dlg.edit_strategy_webhook.mapToGlobal(QPoint(0, 0)))
        test_rect = dlg.btn_strategy_push_test.rect().translated(dlg.btn_strategy_push_test.mapToGlobal(QPoint(0, 0)))

        for rect in (remote_rect, channel_rect, webhook_rect, test_rect):
            self.assertTrue(page_rect.contains(rect), f"{rect} is outside strategy page {page_rect}")
        self.assertFalse(webhook_rect.intersects(test_rect))
        self.assertGreaterEqual(webhook_rect.width(), 220)
        dlg.close()

    def test_strategy_page_sections_stay_inside_scroll_viewport(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 100.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(4)
        dlg.list_strategy_positions.setCurrentRow(0)
        dlg.show()
        self.app.processEvents()

        viewport_rect = dlg.tabs.currentWidget().rect().translated(dlg.tabs.currentWidget().mapToGlobal(QPoint(0, 0)))
        for widget in (dlg.strategy_position_detail, dlg.strategy_rules_group, dlg.strategy_notify_group):
            rect = widget.rect().translated(widget.mapToGlobal(QPoint(0, 0)))
            self.assertLessEqual(rect.right(), viewport_rect.right())
            self.assertGreaterEqual(rect.left(), viewport_rect.left())
        dlg.close()

    def test_strategy_position_and_tier_fields_are_not_clipped(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 149.448, "buy_date": "2026-08-05", "position_pct": 33.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(4)
        dlg.list_strategy_positions.setCurrentRow(0)
        dlg.show()
        self.app.processEvents()

        viewport_rect = dlg.tabs.currentWidget().rect().translated(dlg.tabs.currentWidget().mapToGlobal(QPoint(0, 0)))
        clipped_fields = [
            dlg.edit_strategy_code,
            dlg.spin_strategy_cost,
            dlg.edit_strategy_buy_date,
            dlg.spin_strategy_position_pct,
            dlg.cmb_strategy_profile,
            dlg.btn_strategy_profile_clone,
            *dlg.spin_strategy_tier_profit,
            *dlg.spin_strategy_tier_lock,
        ]
        for widget in clipped_fields:
            rect = widget.rect().translated(widget.mapToGlobal(QPoint(0, 0)))
            self.assertLessEqual(rect.right(), viewport_rect.right(), f"{widget} is clipped on the right")

        for profit, lock in zip(dlg.spin_strategy_tier_profit, dlg.spin_strategy_tier_lock):
            profit_rect = profit.rect().translated(profit.mapToGlobal(QPoint(0, 0)))
            lock_rect = lock.rect().translated(lock.mapToGlobal(QPoint(0, 0)))
            self.assertLess(lock_rect.left() - profit_rect.right(), 40)
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
