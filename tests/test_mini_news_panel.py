import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from MiniNewsPanel import MiniNewsPanel


def news_item(index, important=False):
    return {
        "id": f"news:{index}",
        "title": f"第 {index} 条资讯",
        "summary": "摘要内容",
        "published_at": f"2026-09-20 10:{index:02d}:00",
        "timestamp": index,
        "important": important,
    }


class MiniNewsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_collapsed_view_shows_only_latest_row_and_hover_expands(self):
        panel = MiniNewsPanel()
        panel.apply_config({"mini_items": 2, "mini_opacity": 70, "mini_width": 420, "mini_font_size": 10})
        panel.set_items([news_item(i) for i in range(10)])

        self.assertEqual(panel.ROW_HEIGHT, 93)
        self.assertEqual(panel.EXPANDED_ITEMS, 4)
        self.assertEqual(panel.list_widget.height(), panel.ROW_HEIGHT + 2)
        self.assertEqual(panel.list_widget.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        panel.expand_view()
        self.assertTrue(panel.is_expanded())
        self.assertEqual(panel.list_widget.height(), panel.ROW_HEIGHT * panel.EXPANDED_ITEMS + 2)
        self.assertEqual(panel.list_widget.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)

        panel.list_widget.scrollToBottom()
        panel.collapse_view()
        self.assertFalse(panel.is_expanded())
        self.assertEqual(panel.list_widget.height(), panel.ROW_HEIGHT + 2)
        self.assertEqual(panel.list_widget.verticalScrollBar().value(), 0)
        self.assertEqual(panel.list_widget.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        panel.close()

    def test_important_filter_uses_only_marked_rows(self):
        panel = MiniNewsPanel()
        panel.set_items([news_item(1), news_item(2, important=True)], important_only=True)

        self.assertEqual([item["id"] for item in panel.items()], ["news:2"])
        self.assertEqual(panel.list_widget.count(), 1)
        panel.close()

    def test_mini_list_is_bounded(self):
        panel = MiniNewsPanel()
        panel.set_items([news_item(i) for i in range(80)])

        self.assertEqual(len(panel.items()), panel.MAX_ITEMS)
        self.assertEqual(panel.items()[0]["id"], "news:79")
        panel.close()


if __name__ == "__main__":
    unittest.main()
