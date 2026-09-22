import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from NewsPanel import NewsPanel


class NewsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_timeline_filters_non_important_items_without_losing_cache(self):
        panel = NewsPanel()
        panel.set_items([
            {"id": "sina:2", "title": "重要快讯", "summary": "正文", "published_at": "2026-09-20 10:02:00", "source": "新浪财经", "important": True, "category": "市场", "url": ""},
            {"id": "sina:1", "title": "普通快讯", "summary": "正文", "published_at": "2026-09-20 10:01:00", "source": "新浪财经", "important": False, "category": "公司", "url": ""},
        ])

        self.assertEqual(panel.visible_item_count(), 2)
        panel.set_important_only(True)

        self.assertEqual(panel.visible_item_count(), 1)
        self.assertEqual(len(panel.items()), 2)
        panel.close()

    def test_timeline_groups_items_under_date_heading(self):
        panel = NewsPanel()
        panel.set_items([
            {"id": "sina:2", "title": "第二条", "summary": "", "published_at": "2026-09-20 10:02:00", "source": "新浪财经", "important": False, "category": "", "url": ""},
            {"id": "sina:1", "title": "第一条", "summary": "", "published_at": "2026-09-20 10:01:00", "source": "新浪财经", "important": False, "category": "", "url": ""},
        ])

        self.assertEqual(panel.date_heading_count(), 1)
        self.assertIn("09月20日", panel.date_heading_texts()[0])
        panel.close()

    def test_timeline_loads_large_cache_in_batches(self):
        panel = NewsPanel()
        panel.set_items([
            {"id": f"sina:{idx}", "title": f"消息{idx}", "summary": "", "published_at": "2026-09-20 10:02:00", "timestamp": idx, "source": "新浪财经", "important": False, "category": "", "url": ""}
            for idx in range(260)
        ])

        self.assertEqual(len(panel.items()), 260)
        self.assertEqual(panel.visible_item_count(), 15)
        self.assertTrue(panel.load_more_button.isVisibleTo(panel.content))

        panel._load_more()

        self.assertEqual(panel.visible_item_count(), 30)
        panel.close()

    def test_important_items_use_red_visual_roles(self):
        panel = NewsPanel()
        panel.set_items([{
            "id": "sina:important", "title": "重要消息", "summary": "正文",
            "published_at": "2026-09-20 10:02:00", "timestamp": 1,
            "source": "新浪财经", "important": True, "category": "市场", "url": "",
        }])

        object_names = {label.objectName() for label in panel.content.findChildren(QLabel)}

        self.assertIn("importantNewsTime", object_names)
        self.assertIn("importantNewsTitle", object_names)
        self.assertIn("importantNewsSummary", object_names)
        panel.close()

    def test_mute_button_can_restore_notifications(self):
        panel = NewsPanel()
        changes = []
        panel.mute_today_changed.connect(changes.append)

        panel.set_muted_today(True)
        self.assertTrue(panel.mute_button.isEnabled())
        self.assertEqual(panel.mute_button.text(), "恢复今日弹出")
        panel.mute_button.click()

        self.assertEqual(changes, [False])
        self.assertFalse(panel.is_muted_today())
        panel.close()

    def test_news_window_is_not_topmost_until_pin_is_enabled(self):
        panel = NewsPanel()

        self.assertFalse(bool(panel.windowFlags() & Qt.WindowStaysOnTopHint))
        panel.set_pinned(True)

        self.assertTrue(bool(panel.windowFlags() & Qt.WindowStaysOnTopHint))
        self.assertTrue(panel.pin_button.isChecked())
        panel.close()

    def test_manual_open_restores_minimized_window(self):
        panel = NewsPanel()
        panel.showMinimized()
        self.app.processEvents()

        panel.show_news(auto_show=False)
        self.app.processEvents()

        self.assertTrue(panel.isVisible())
        self.assertFalse(panel.isMinimized())
        panel.close()

    def test_auto_show_does_not_raise_or_activate_window(self):
        panel = NewsPanel()
        calls = []
        panel.show = lambda: calls.append("show")
        panel.raise_ = lambda: calls.append("raise")
        panel.activateWindow = lambda: calls.append("activate")

        panel.show_news(auto_show=True)

        self.assertEqual(calls, ["show"])
        self.assertTrue(panel.testAttribute(Qt.WA_ShowWithoutActivating))
        panel.close()

    def test_setting_same_importance_filter_does_not_rebuild(self):
        panel = NewsPanel()
        rebuilds = []
        panel._rebuild = lambda: rebuilds.append(True)

        panel.set_important_only(False)

        self.assertEqual(rebuilds, [])
        panel.close()


if __name__ == "__main__":
    unittest.main()
