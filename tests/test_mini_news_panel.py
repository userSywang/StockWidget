import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from MiniNewsPanel import MiniNewsPanel, RollingNewsLabel


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

    def test_idle_view_is_single_line_island_and_hover_shows_history(self):
        panel = MiniNewsPanel()
        panel.apply_config({"mini_items": 2, "mini_opacity": 70, "mini_width": 420, "mini_font_size": 10})
        panel.set_items([news_item(i) for i in range(10)])

        self.assertEqual(panel.height(), panel.IDLE_HEIGHT)
        self.assertTrue(panel.ticker.isVisibleTo(panel))
        self.assertFalse(panel.header_widget.isVisibleTo(panel))
        self.assertFalse(panel.list_widget.isVisibleTo(panel))
        self.assertFalse(hasattr(panel, "close_button"))
        self.assertIn("第 9 条资讯", panel.ticker.current_source_text())
        self.assertEqual(panel.ticker.message_count(), 10)

        panel.expand_view()
        self.assertTrue(panel.is_expanded())
        self.assertFalse(panel.ticker.isVisibleTo(panel))
        self.assertTrue(panel.header_widget.isVisibleTo(panel))
        self.assertTrue(panel.list_widget.isVisibleTo(panel))
        self.assertEqual(panel.list_widget.height(), panel.ROW_HEIGHT * panel.EXPANDED_ITEMS + 2)
        self.assertEqual(panel.list_widget.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)

        panel.list_widget.scrollToBottom()
        panel.collapse_view()
        self.assertFalse(panel.is_expanded())
        self.assertEqual(panel.height(), panel.IDLE_HEIGHT)
        self.assertTrue(panel.ticker.isVisibleTo(panel))
        self.assertFalse(panel.header_widget.isVisibleTo(panel))
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

    def test_rolling_messages_switch_items_and_fit_available_pixel_width(self):
        label = RollingNewsLabel()
        label.resize(220, 30)
        label.show()
        QApplication.processEvents()
        label.set_messages([
            {"text": "甲" * 240, "color": "#eef1f5"},
            {"text": "第二条资讯", "color": "#ff665e"},
        ])
        narrow = label.current_display_text()

        label.resize(440, 30)
        QApplication.processEvents()
        wide = label.current_display_text()

        self.assertTrue(narrow.endswith("…"))
        self.assertTrue(wide.endswith("…"))
        self.assertGreater(len(wide), len(narrow))
        self.assertLessEqual(label.fontMetrics().horizontalAdvance(wide), label.content_width())

        label.show_next_message(immediate=True)
        self.assertEqual(label.current_source_text(), "第二条资讯")
        label.close()


if __name__ == "__main__":
    unittest.main()
