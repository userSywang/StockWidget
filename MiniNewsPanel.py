from datetime import datetime

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MiniNewsPanel(QWidget):
    MAX_ITEMS = 50
    EXPANDED_ITEMS = 6
    ROW_HEIGHT = 62

    open_full_requested = Signal()
    disable_requested = Signal()
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._items = []
        self._collapsed_items = 1
        self._background_alpha = 190
        self._expanded = False
        self._drag_offset = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.title_label = QLabel("实时资讯")
        self.title_label.setObjectName("miniNewsTitle")
        self.status_label = QLabel("最新")
        self.status_label.setObjectName("miniNewsStatus")
        header.addWidget(self.title_label)
        header.addWidget(self.status_label)
        header.addStretch(1)
        self.expand_button = QPushButton("展开")
        self.expand_button.setObjectName("miniNewsButton")
        self.expand_button.clicked.connect(self.open_full_requested.emit)
        header.addWidget(self.expand_button)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("miniNewsClose")
        self.close_button.setToolTip("关闭迷你资讯")
        self.close_button.clicked.connect(self.disable_requested.emit)
        header.addWidget(self.close_button)
        root.addLayout(header)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("miniNewsList")
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.open_full_requested.emit())
        root.addWidget(self.list_widget)

        self.setStyleSheet("""
            QLabel#miniNewsTitle { color: #ffffff; font-weight: 600; }
            QLabel#miniNewsStatus { color: #aeb7c6; }
            QListWidget#miniNewsList { background: transparent; border: 0; outline: 0; color: #eef1f5; }
            QListWidget#miniNewsList::item { border-bottom: 1px solid rgba(255,255,255,28); padding: 5px 2px; }
            QPushButton#miniNewsButton, QPushButton#miniNewsClose { color: #d9dee8; background: rgba(255,255,255,18); border: 0; padding: 3px 7px; }
            QPushButton#miniNewsButton:hover, QPushButton#miniNewsClose:hover { background: rgba(255,255,255,40); }
        """)
        self._update_height()

    def apply_config(self, config):
        self._collapsed_items = 2 if int(config.get("mini_items", 1)) == 2 else 1
        opacity = max(20, min(100, int(config.get("mini_opacity", 75))))
        self._background_alpha = round(255 * opacity / 100)
        width = max(320, min(620, int(config.get("mini_width", 420))))
        font_size = max(9, min(14, int(config.get("mini_font_size", 10))))
        self.setFixedWidth(width)
        self.setFont(QFont("Microsoft YaHei", font_size))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(config.get("mini_pinned", True)))
        self._update_height()
        self.update()

    def set_items(self, items, important_only=False):
        rows = [dict(item) for item in items or [] if isinstance(item, dict) and item.get("id")]
        rows.sort(key=lambda item: int(item.get("timestamp") or 0), reverse=True)
        if important_only:
            rows = [item for item in rows if item.get("important")]
        self._items = rows[:self.MAX_ITEMS]
        self.list_widget.clear()
        for row in self._items:
            item = QListWidgetItem(self._item_text(row))
            item.setSizeHint(QSize(0, self.ROW_HEIGHT))
            item.setForeground(QColor("#ff665e" if row.get("important") else "#eef1f5"))
            item.setToolTip(str(row.get("title") or ""))
            self.list_widget.addItem(item)
        if not self._items:
            empty = QListWidgetItem("暂无符合条件的消息")
            empty.setSizeHint(QSize(0, self.ROW_HEIGHT))
            empty.setForeground(QColor("#aeb7c6"))
            self.list_widget.addItem(empty)
        self.list_widget.scrollToTop()
        self.status_label.setText(self._latest_time())
        self._update_height()

    def items(self):
        return list(self._items)

    def is_expanded(self):
        return self._expanded

    def expand_view(self):
        if self._expanded:
            return
        self._expanded = True
        self._update_height()

    def collapse_view(self):
        self._expanded = False
        self.list_widget.scrollToTop()
        self._update_height()

    def show_mini(self, anchor=None):
        if not self.isVisible():
            target_screen = QApplication.screenAt(anchor.frameGeometry().center()) if anchor is not None else None
            target_screen = target_screen or QApplication.primaryScreen()
            available = target_screen.availableGeometry()
            self.move(available.right() - self.width() - 18, available.top() + 80)
            self.show()
        self.raise_()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.expand_view()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        QTimer.singleShot(220, self._collapse_if_outside)

    def _collapse_if_outside(self):
        if not self.underMouse():
            self.collapse_view()

    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 38:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor(255, 255, 255, 32))
        painter.setBrush(QColor(20, 24, 31, self._background_alpha))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        super().paintEvent(event)

    def _update_height(self):
        count = self.EXPANDED_ITEMS if self._expanded else self._collapsed_items
        available = max(1, min(count, max(1, self.list_widget.count())))
        self.list_widget.setFixedHeight(available * self.ROW_HEIGHT + 2)
        self.setFixedHeight(self.list_widget.height() + 50)

    def _latest_time(self):
        if not self._items:
            return "暂无消息"
        raw = str(self._items[0].get("published_at") or "")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(raw, fmt).strftime("%H:%M")
            except ValueError:
                continue
        return raw[-5:] if raw else "最新"

    @staticmethod
    def _item_text(item):
        raw = str(item.get("published_at") or "")
        time_text = raw[11:16] if len(raw) >= 16 else raw[-5:]
        title = " ".join(str(item.get("title") or "财经快讯").split())
        summary = " ".join(str(item.get("summary") or "").split())
        first = f"{time_text}  {title}" if time_text else title
        if summary and summary != title:
            return first + "\n" + summary[:64]
        return first
