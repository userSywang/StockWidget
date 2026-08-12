import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QSpinBox
from PySide6.QtCore import QPoint, Qt, QEvent

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
        self.strategy_alert_history = []
        self.code_tags = {}
        self.warning_visible = False
        self.warning_text = ""
        self.market_amount_visible = False
        self.price_alert_badge_visible = True
        self._latest_price_alert_states = {}
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

    def set_price_alert_badge_visible(self, visible):
        self.price_alert_badge_visible = bool(visible)

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

        self.assertEqual(dlg.tabs.currentIndex(), 0)
        self.assertEqual(win.price_alerts[0]["code"], "sh603259")
        self.assertEqual(dlg.list_price_alerts.currentRow(), 0)
        self.assertEqual(dlg.edit_price_alert_code.text(), "sh603259")
        self.assertTrue(dlg.edit_price_alert_code.isHidden())
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

        self.assertEqual(dlg.tabs.currentIndex(), 2)
        self.assertEqual(win.strategy_alert_config["positions"][0]["code"], "sh603259")
        self.assertEqual(dlg.list_strategy_positions.currentRow(), 0)
        self.assertEqual(dlg.edit_strategy_code.text(), "sh603259")
        self.assertTrue(dlg.edit_strategy_code.hasSelectedText())
        dlg.close()

    def test_alert_and_strategy_lists_show_stock_short_names(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
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

    def test_self_selected_buttons_keep_generic_text_and_enable_jump(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        dlg = SettingsDialog(win, None)

        code_item = dlg.tree_codes.topLevelItem(0).child(0)
        dlg.tree_codes.setCurrentItem(code_item)

        self.assertEqual(dlg.btn_code_to_alert.text(), "设提醒")
        self.assertEqual(dlg.btn_code_to_strategy.text(), "设策略")
        self.assertTrue(dlg.btn_code_to_alert.isHidden())
        self.assertTrue(dlg.btn_code_to_strategy.isEnabled())
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

    def test_self_selected_code_tag_controls_do_not_overlap_buttons(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        dlg = SettingsDialog(win, None)
        dlg.show()
        self.app.processEvents()

        def global_rect(widget):
            rect = widget.rect()
            rect.moveTopLeft(widget.mapToGlobal(QPoint(0, 0)))
            return rect

        buttons = [
            dlg.btn_add,
            dlg.btn_add_group,
            dlg.btn_del,
            dlg.btn_up,
            dlg.btn_dn,
            dlg.btn_code_to_strategy,
        ]
        combos = [dlg.cmb_code_holding, dlg.cmb_code_cycle, dlg.cmb_code_priority]
        for button in buttons:
            for combo in combos:
                self.assertFalse(global_rect(button).intersects(global_rect(combo)))
        list_rect = global_rect(dlg.tree_codes)
        for combo in combos:
            combo_rect = global_rect(combo)
            self.assertGreater(combo_rect.top(), list_rect.bottom())
        dlg.close()

    def test_self_selected_list_has_expanded_display_area(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        self.assertLessEqual(dlg.tab_sizes[0].width(), 460)
        self.assertGreaterEqual(dlg.tab_sizes[0].width(), 420)
        self.assertGreaterEqual(dlg.tab_sizes[0].height(), 420)
        self.assertGreaterEqual(dlg.tree_codes.minimumWidth(), 300)
        self.assertGreaterEqual(dlg.tree_codes.minimumHeight(), 250)
        dlg.close()

    def test_strategy_library_uses_fixed_strategy_editors(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        dlg.tabs.setCurrentIndex(2)

        self.assertGreaterEqual(dlg.width(), 600)
        self.assertLessEqual(dlg.width(), 660)
        self.assertGreater(dlg.maximumWidth(), dlg.width())
        self.assertLessEqual(dlg.list_strategy_templates.width(), 170)
        self.assertTrue(dlg.btn_template_new.isHidden())
        self.assertTrue(dlg.btn_template_copy.isHidden())
        self.assertTrue(dlg.btn_template_delete.isHidden())
        self.assertTrue(dlg.condition_builder_group.isHidden())
        self.assertTrue(dlg.table_template_action_rules.isHidden())
        dlg.close()

    def test_display_data_page_includes_ma_and_strategy_columns(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        labels = {cb.text() for cb in dlg.cbs}

        self.assertTrue({"MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"}.issubset(labels))
        self.assertTrue(dlg.chk_price_alert_badge_visible.isChecked())
        dlg.chk_price_alert_badge_visible.setChecked(False)
        self.assertFalse(win.price_alert_badge_visible)
        self.assertFalse(hasattr(dlg, "chk_price_alert_badge_visible_inline"))
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

    def test_price_alert_editor_is_embedded_in_self_selected_page(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(0)
        dlg.show()
        self.app.processEvents()

        add_rect = dlg.btn_price_alert_add.rect().translated(dlg.btn_price_alert_add.mapToGlobal(QPoint(0, 0)))
        del_rect = dlg.btn_price_alert_del.rect().translated(dlg.btn_price_alert_del.mapToGlobal(QPoint(0, 0)))

        self.assertEqual(dlg.tabs.currentIndex(), 0)
        self.assertTrue(dlg.btn_code_to_alert.isHidden())
        self.assertTrue(dlg.list_price_alerts.isHidden())
        self.assertTrue(dlg.btn_price_alert_add.isVisible())
        self.assertTrue(dlg.btn_price_alert_del.isVisible())
        self.assertFalse(hasattr(dlg, "chk_price_alert_enabled"))
        self.assertFalse(hasattr(dlg, "chk_price_alert_badge_visible_inline"))
        self.assertTrue(dlg.edit_price_alert_code.isHidden())
        self.assertGreaterEqual(del_rect.left(), add_rect.right())
        self.assertEqual(dlg.btn_price_alert_add.text(), "保存")
        self.assertIn("sh603259", dlg.lbl_price_alert_current.text())
        self.assertEqual(dlg.edit_price_alert_code.text(), "sh603259")
        dlg.close()

    def test_self_selected_page_contains_price_alert_editor_and_no_alert_tab(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        tab_names = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]

        self.assertNotIn("提醒", tab_names)
        self.assertEqual(tab_names[-1], "数据源")
        self.assertLessEqual(dlg.tab_sizes[0].width(), 460)
        self.assertGreater(dlg.maximumWidth(), dlg.width())
        self.assertTrue(dlg.list_price_alerts.isHidden())
        self.assertLessEqual(dlg.edit_price_alert_message.minimumWidth(), 160)
        self.assertEqual(dlg.edit_price_alert_message.placeholderText(), "备注，可空")
        dlg.close()

    def test_price_alerts_can_be_added_edited_and_deleted(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        dlg = SettingsDialog(win, None)
        code_item = dlg.tree_codes.topLevelItem(0).child(0)
        dlg.tree_codes.setCurrentItem(code_item)

        self.assertIsNone(code_item.data(0, Qt.UserRole + 3))
        dlg._add_price_alert()
        self.assertEqual(dlg.list_price_alerts.count(), 1)
        self.assertEqual(win.price_alerts[0]["code"], "sh603259")
        self.assertTrue(win.price_alerts[0]["enabled"])
        self.assertEqual(win.price_alerts[0]["expire_days"], 30)
        self.assertIsNone(code_item.data(0, Qt.UserRole + 3))

        dlg.cmb_price_alert_direction.setCurrentIndex(dlg.cmb_price_alert_direction.findData("below_ma5"))
        dlg.cmb_price_alert_expire_days.setCurrentIndex(dlg.cmb_price_alert_expire_days.findData(5))
        dlg.spin_price_alert_price.setValue(1.234)
        dlg.edit_price_alert_message.setText("跌破提醒")
        dlg._on_price_alert_editor_changed()

        self.assertEqual(win.price_alerts[0]["code"], "sh603259")
        self.assertEqual(win.price_alerts[0]["direction"], "below_ma5")
        self.assertFalse(dlg.spin_price_alert_price.isEnabled())
        self.assertEqual(win.price_alerts[0]["message"], "跌破提醒")
        self.assertEqual(win.price_alerts[0]["expire_days"], 5)

        dlg._del_price_alert()
        self.assertEqual(win.price_alerts, [])
        self.assertIsNone(code_item.data(0, Qt.UserRole + 3))
        dlg.close()

    def test_self_selected_tree_does_not_show_price_alert_badge(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.price_alerts = [{"enabled": True, "code": "sh603259", "direction": "below", "price": 145.0, "message": ""}]
        win._latest_price_alert_states = {"sh603259": [{"triggered": True}]}
        dlg = SettingsDialog(win, None)
        code_item = dlg.tree_codes.topLevelItem(0).child(0)

        self.assertIsNone(code_item.data(0, Qt.UserRole + 3))
        self.assertFalse(hasattr(dlg, "_refresh_price_alert_icons"))
        dlg.close()

    def test_strategy_page_edits_positions_and_rules(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh000001", "sh512000"]}]
        win.codes = ["sh000001", "sh512000"]
        win.checked_codes = ["sh000001", "sh512000"]
        dlg = SettingsDialog(win, None)

        dlg.tabs.setCurrentIndex(2)
        dlg._add_strategy_position()
        self.assertEqual(dlg.list_strategy_positions.count(), 1)

        dlg.edit_strategy_code.setText("512000")
        dlg.spin_strategy_cost.setValue(1.234)
        dlg.edit_strategy_buy_date.setText("2026-08-05")
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
        self.assertNotIn("position_pct", win.strategy_alert_config["positions"][0])
        self.assertEqual(win.strategy_alert_config["positions"][0]["note"], "测试持仓")
        self.assertTrue(win.strategy_alert_config["notifications"]["desktop_popup"])
        self.assertTrue(win.strategy_alert_config["notifications"]["panel_highlight"])
        self.assertTrue(win.strategy_alert_config["notifications"]["remote_push"])
        self.assertEqual(win.strategy_alert_config["notifications"]["remote_channel"], "wecom")
        self.assertEqual(win.strategy_alert_config["notifications"]["webhook_url"], "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
        self.assertEqual(win.strategy_alert_config["notifications"]["daily_summary_time"], "09:00,18:00")
        self.assertEqual(win.strategy_alert_config["positions"][0]["rules"]["max_loss_pct"], 6.0)
        self.assertEqual(win.strategy_alert_config["positions"][0]["rules"]["stale_position_days"], 10)
        preview = [dlg.list_strategy_preview.item(i).text() for i in range(dlg.list_strategy_preview.count())]
        self.assertTrue(any("桌面弹窗" in row and "远程推送" in row for row in preview))
        self.assertTrue(any("交易日 09:00、18:00 远程推送" in row for row in preview))
        self.assertTrue(any("30 分钟内不重复推送" in row for row in preview))
        self.assertTrue(any("浮亏达到 6.0%" in row for row in preview))

        dlg._del_strategy_position()
        self.assertEqual(win.strategy_alert_config["positions"], [])
        dlg.close()

    def test_strategy_pages_remove_position_size_and_cap_controls(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        self.assertFalse(hasattr(dlg, "spin_strategy_position_pct"))
        self.assertFalse(hasattr(dlg, "spin_strategy_max_position"))
        self.assertFalse(hasattr(dlg, "chk_strategy_block_heavy"))
        self.assertFalse(hasattr(dlg, "spin_template_max_position"))
        self.assertFalse(hasattr(dlg, "chk_template_block_heavy"))
        dlg.close()

    def test_add_strategy_position_defaults_buy_date_to_today(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh512000"]}]
        win.codes = ["sh512000"]
        win.checked_codes = ["sh512000"]
        dlg = SettingsDialog(win, None)

        with patch("SettingPanel.date") as fake_date:
            fake_date.today.return_value = date(2026, 8, 12)
            dlg._add_strategy_position()

        self.assertEqual(dlg.edit_strategy_buy_date.text(), "2026-08-12")
        self.assertEqual(win.strategy_alert_config["positions"][0]["buy_date"], "2026-08-12")
        dlg.close()

    def test_strategy_rules_follow_selected_position_and_save_to_position(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh512000", "sh000001"]}]
        win.codes = ["sh512000", "sh000001"]
        win.checked_codes = ["sh512000", "sh000001"]
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

    def test_strategy_library_shows_builtin_turtle_template(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)

        items = [
            (dlg.list_strategy_templates.item(i).data(Qt.UserRole), dlg.list_strategy_templates.item(i).text())
            for i in range(dlg.list_strategy_templates.count())
        ]
        turtle_items = [text for profile_id, text in items if profile_id == "turtle:classic"]
        turtle_row = next(i for i, (profile_id, _text) in enumerate(items) if profile_id == "turtle:classic")

        self.assertEqual(len(turtle_items), 1)
        self.assertIn("4条", turtle_items[0])
        dlg.list_strategy_templates.setCurrentRow(turtle_row)
        self.assertFalse(dlg.template_rules_scroll.isHidden())
        self.assertTrue(dlg.template_action_group.isHidden())
        self.assertTrue(dlg.g_template_profit.isHidden())
        self.assertFalse(dlg.g_template_turtle.isHidden())
        self.assertFalse(dlg.g_turtle_entry.isHidden())
        self.assertFalse(dlg.g_turtle_stop.isHidden())
        self.assertFalse(dlg.g_turtle_exit.isHidden())
        self.assertEqual(dlg.g_turtle_entry.title(), "入场策略")
        self.assertEqual(dlg.g_turtle_stop.title(), "止损策略")
        self.assertEqual(dlg.g_turtle_exit.title(), "止盈/退出策略")
        self.assertTrue(dlg.table_template_action_rules.isHidden())
        self.assertFalse(dlg.spin_turtle_entry_days.isHidden())

        dlg.show()
        self.app.processEvents()
        group_left = dlg.g_template_turtle.mapToGlobal(QPoint(0, 0)).x()
        group_right = group_left + dlg.g_template_turtle.width()
        for editor in (
            dlg.spin_turtle_entry_days,
            dlg.spin_turtle_exit_days,
            dlg.spin_turtle_atr_stop,
            dlg.spin_turtle_pyramid_atr,
            dlg.spin_turtle_max_units,
            dlg.cmb_turtle_sizing,
        ):
            editor_left = editor.mapToGlobal(QPoint(0, 0)).x()
            editor_right = editor_left + editor.width()
            self.assertGreaterEqual(editor_left, group_left)
            self.assertLessEqual(editor_right, group_right)
            self.assertLess(editor_left - group_left, 170)
        self.assertLessEqual(dlg.g_template_turtle.sizeHint().width(), 360)
        self.assertLessEqual(dlg.g_turtle_entry.layout().spacing(), 6)
        self.assertLessEqual(dlg.g_turtle_stop.layout().spacing(), 6)
        self.assertLessEqual(dlg.g_turtle_exit.layout().spacing(), 6)

        dlg.spin_turtle_entry_days.setValue(55)
        dlg.spin_turtle_exit_days.setValue(20)
        dlg.spin_turtle_atr_stop.setValue(3.0)
        dlg.spin_turtle_pyramid_atr.setValue(1.0)
        dlg.spin_turtle_max_units.setValue(3)
        dlg.cmb_turtle_sizing.setCurrentIndex(dlg.cmb_turtle_sizing.findData("fixed_percent"))
        dlg._on_template_save()

        profile = next(item for item in win.strategy_alert_config["strategy_profiles"] if item["id"] == "turtle:classic")
        rules = {rule["id"]: rule for rule in profile["action_rules"]}
        self.assertEqual(profile["turtle_params"]["entry_days"], 55)
        self.assertEqual(profile["turtle_params"]["position_sizing"], "fixed_percent")
        self.assertEqual(rules["turtle_entry_20d"]["parameter"], {"value": 55, "unit": "day_high"})
        self.assertEqual(rules["turtle_entry_20d"]["condition"]["threshold"]["period"], 55)
        self.assertEqual(rules["turtle_exit_10d"]["parameter"], {"value": 20, "unit": "day_low"})
        self.assertEqual(rules["turtle_atr_stop"]["condition"]["threshold"]["multiple"], 3.0)
        self.assertEqual(rules["turtle_pyramid_0_5atr"]["action"]["max_units"], 3)
        dlg.close()

    def test_strategy_rule_edits_do_not_change_other_default_positions(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259", "sh600584"]}]
        win.codes = ["sh603259", "sh600584"]
        win.checked_codes = ["sh603259", "sh600584"]
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

    def test_strategy_cost_edit_sends_line_change_alert_and_keeps_state(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        pushed = []
        win.show_desktop_alert = lambda text: pushed.append(text)
        win._send_strategy_push_text = lambda text: pushed.append(text) or True
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {"desktop_popup": True, "remote_push": True, "webhook_url": "https://example.test"},
            "positions": [{
                "code": "sh603259",
                "cost_price": 100.0,
                "locked_profit_pct": 10.0,
                "last_stop_price": 110.0,
            }],
        }
        dlg = SettingsDialog(win, None)
        dlg.list_strategy_positions.setCurrentRow(0)

        dlg.spin_strategy_cost.setValue(120.0)
        dlg._save_strategy_position()

        position = win.strategy_alert_config["positions"][0]
        self.assertEqual(position["last_stop_price"], 132.0)
        self.assertEqual(position["locked_profit_pct"], 10.0)
        self.assertTrue(any("药明康德止盈线变化" in text for text in pushed))
        self.assertTrue(any("标的：药明康德" in text for text in pushed))
        self.assertTrue(any("110.00 -> 132.00" in text for text in pushed))
        self.assertTrue(any("止盈线：110.00 -> 132.00" in text for text in pushed))
        self.assertFalse(any("重要提醒" in text for text in pushed))
        self.assertFalse(any("止盈/止损线" in text for text in pushed))
        dlg.close()

    def test_new_strategy_position_save_alerts_initial_stop_line_and_logs(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        pushed = []
        remote_pushed = []
        win.show_desktop_alert = lambda text: pushed.append(text)
        win._send_strategy_push_text = lambda text: remote_pushed.append(text) or True
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {"desktop_popup": True, "remote_push": True, "webhook_url": "https://example.test"},
            "positions": [],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)

        dlg._add_strategy_position()
        dlg.spin_strategy_cost.setValue(100.0)
        dlg.spin_strategy_loss.setValue(5.0)
        dlg._save_strategy_position()

        position = win.strategy_alert_config["positions"][0]
        self.assertEqual(position["last_stop_price"], 95.0)
        self.assertTrue(any("药明康德策略套用" in text for text in pushed))
        self.assertTrue(any("止损线：95.00" in text for text in pushed))
        self.assertTrue(any("药明康德策略套用" in text for text in remote_pushed))
        self.assertEqual(win.strategy_alert_history[0]["code"], "sh603259")
        self.assertIn("策略套用", win.strategy_alert_history[0]["status"])
        dlg.close()

    def test_strategy_loss_threshold_save_alerts_change_and_logs_after_live_edit(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        pushed = []
        remote_pushed = []
        win.show_desktop_alert = lambda text: pushed.append(text)
        win._send_strategy_push_text = lambda text: remote_pushed.append(text) or True
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {"desktop_popup": True, "remote_push": True, "webhook_url": "https://example.test"},
            "positions": [{
                "code": "sh603259",
                "cost_price": 100.0,
                "last_stop_price": 90.0,
                "rules": {"max_loss_enabled": True, "max_loss_pct": 10.0},
            }],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
        dlg.list_strategy_positions.setCurrentRow(0)

        dlg.spin_strategy_loss.setValue(5.0)
        dlg._save_strategy_position()

        position = win.strategy_alert_config["positions"][0]
        self.assertEqual(position["last_stop_price"], 95.0)
        self.assertTrue(any("浮亏清仓阈值：10.0% → 5.0%" in text for text in pushed))
        self.assertTrue(any("药明康德止损线变化" in text for text in pushed))
        self.assertTrue(any("90.00 -> 95.00" in text for text in pushed))
        self.assertTrue(any("浮亏清仓阈值：10.0% → 5.0%" in text for text in remote_pushed))
        self.assertTrue(any("药明康德止损线变化" in text for text in remote_pushed))
        self.assertTrue(any("策略修改" in item["status"] for item in win.strategy_alert_history))
        self.assertTrue(any("止损线变化" in item["status"] for item in win.strategy_alert_history))
        dlg.close()

    def test_strategy_params_save_sends_alerts_and_webhook(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.code_names = {"sh603259": "药明康德"}
        pushed = []
        remote_pushed = []
        win.show_desktop_alert = lambda text: pushed.append(text)
        win._send_strategy_push_text = lambda text: remote_pushed.append(text) or True
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {"desktop_popup": True, "remote_push": True, "webhook_url": "https://example.test"},
            "positions": [{
                "code": "sh603259",
                "cost_price": 100.0,
                "last_stop_price": 90.0,
                "rules": {"max_loss_enabled": True, "max_loss_pct": 10.0},
            }],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
        dlg.list_strategy_positions.setCurrentRow(0)

        dlg._on_strategy_params_edit()
        dlg.spin_strategy_loss.setValue(5.0)
        dlg._on_strategy_params_save()

        self.assertEqual(win.strategy_alert_config["positions"][0]["last_stop_price"], 95.0)
        self.assertTrue(any("浮亏清仓阈值：10.0% → 5.0%" in text for text in pushed))
        self.assertTrue(any("药明康德止损线变化" in text for text in pushed))
        self.assertTrue(any("浮亏清仓阈值：10.0% → 5.0%" in text for text in remote_pushed))
        self.assertTrue(any("药明康德止损线变化" in text for text in remote_pushed))
        self.assertTrue(any("止损线变化" in item["status"] for item in win.strategy_alert_history))
        dlg.close()

    def test_strategy_history_log_shows_all_recent_triggers(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh603259", "sh600584"]}]
        win.codes = ["sh603259", "sh600584"]
        win.checked_codes = ["sh603259", "sh600584"]
        win.strategy_alert_history = [
            {"time": "2026-08-10 10:00", "code": "sh603259", "name": "药明康德", "status": "触发止损"},
            {"time": "2026-08-10 10:01", "code": "sh600584", "name": "长电科技", "status": "止盈线变化"},
        ]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [
                {"code": "sh603259", "cost_price": 100.0},
                {"code": "sh600584", "cost_price": 30.0},
            ],
        }
        dlg = SettingsDialog(win, None)

        dlg.list_strategy_positions.setCurrentRow(0)
        rows = [dlg.list_strategy_history.item(i).text() for i in range(dlg.list_strategy_history.count())]

        self.assertTrue(any("药明康德" in row for row in rows))
        self.assertTrue(any("长电科技" in row for row in rows))
        self.assertEqual(dlg.strategy_subtabs.tabText(2), "触发日志")
        dlg.close()

    def test_spin_boxes_ignore_wheel_when_not_focused(self):
        win = FakeWindow()
        dlg = SettingsDialog(win, None)
        spin_boxes = dlg.findChildren(QSpinBox) + dlg.findChildren(QDoubleSpinBox)
        self.assertGreater(len(spin_boxes), 0)

        for spin in spin_boxes:
            spin.clearFocus()
            event = QEvent(QEvent.Wheel)
            self.assertTrue(dlg.eventFilter(spin, event))
        dlg.close()

    def test_combo_boxes_ignore_wheel_when_not_focused(self):
        win = FakeWindow()
        win.strategy_alert_config = {
            "enabled": True,
            "notifications": {"remote_push": True, "remote_channel": "wecom", "webhook_url": "https://example.test"},
        }
        dlg = SettingsDialog(win, None)
        combo_boxes = dlg.findChildren(QComboBox)
        self.assertGreater(len(combo_boxes), 0)

        dlg.cmb_strategy_remote_channel.setCurrentIndex(dlg.cmb_strategy_remote_channel.findData("wecom"))
        dlg.cmb_strategy_remote_channel.clearFocus()
        event = QEvent(QEvent.Wheel)

        self.assertTrue(dlg.eventFilter(dlg.cmb_strategy_remote_channel, event))
        self.assertEqual(dlg.cmb_strategy_remote_channel.currentData(), "wecom")
        dlg.close()

    def test_strategy_page_removes_positions_not_in_self_selected_codes(self):
        win = FakeWindow()
        win.codes = ["sh603259"]
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [
                {"code": "sh603259", "cost_price": 100.0},
                {"code": "sz000636", "cost_price": 1.0},
            ],
        }

        dlg = SettingsDialog(win, None)

        self.assertEqual([p["code"] for p in win.strategy_alert_config["positions"]], ["sh603259"])
        self.assertEqual(dlg.list_strategy_positions.count(), 1)
        dlg.close()

    def test_strategy_editor_rejects_code_outside_self_selected_list(self):
        win = FakeWindow()
        win.codes = ["sh603259"]
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.checked_codes = ["sh603259"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 100.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.list_strategy_positions.setCurrentRow(0)

        dlg.edit_strategy_code.setText("000636")
        dlg._on_strategy_position_editor_changed()

        self.assertEqual(win.strategy_alert_config["positions"][0]["code"], "sh603259")
        self.assertEqual(dlg.edit_strategy_code.text(), "sh603259")
        dlg.close()

    def test_strategy_rules_are_hidden_until_a_position_is_selected(self):
        win = FakeWindow()
        win.groups = [{"name": "默认", "codes": ["sh512000"]}]
        win.codes = ["sh512000"]
        win.checked_codes = ["sh512000"]
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
        win.groups = [{"name": "默认", "codes": ["sh512000"]}]
        win.codes = ["sh512000"]
        win.checked_codes = ["sh512000"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh512000", "cost_price": 1.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
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
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 100.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
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
        dlg.tabs.setCurrentIndex(2)
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
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 100.0}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
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
        win.groups = [{"name": "默认", "codes": ["sh603259"]}]
        win.codes = ["sh603259"]
        win.checked_codes = ["sh603259"]
        win.strategy_alert_config = {
            "enabled": True,
            "positions": [{"code": "sh603259", "cost_price": 149.448, "buy_date": "2026-08-05"}],
        }
        dlg = SettingsDialog(win, None)
        dlg.tabs.setCurrentIndex(2)
        dlg.list_strategy_positions.setCurrentRow(0)
        dlg.show()
        self.app.processEvents()

        viewport_rect = dlg.tabs.currentWidget().rect().translated(dlg.tabs.currentWidget().mapToGlobal(QPoint(0, 0)))
        clipped_fields = [
            dlg.edit_strategy_code,
            dlg.spin_strategy_cost,
            dlg.edit_strategy_buy_date,
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
