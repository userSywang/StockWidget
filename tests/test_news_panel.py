import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
