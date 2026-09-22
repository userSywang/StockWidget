from datetime import datetime

from PySide6.QtCore import Qt, Signal, QSize, QElapsedTimer, QTimer
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


class RollingNewsLabel(QWidget):
    ANIMATION_INTERVAL_MS = 16
    ANIMATION_DURATION_MS = 260

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages = []
        self._index = 0
        self._next_index = None
        self._progress = 0.0
        self._elapsed = QElapsedTimer()
        self.setAccessibleName("最新实时资讯")
        self.setFixedHeight(28)
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(self.ANIMATION_INTERVAL_MS)
        self._animation_timer.timeout.connect(self._animate)

    def set_messages(self, messages):
        rows = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            text = " ".join(str(message.get("text") or "").split())
            if not text:
                continue
            rows.append({
                "id": str(message.get("id") or text),
                "text": text,
                "color": QColor(message.get("color") or "#eef1f5"),
            })
        if rows == self._messages:
            return
        old_latest_id = self._messages[0]["id"] if self._messages else ""
        if self._next_index is not None:
            self._index = self._next_index
            self._next_index = None
            self._progress = 0.0
            self._animation_timer.stop()
        current_id = self._messages[self._index]["id"] if self._messages else ""
        self._messages = rows
        current_index = next(
            (index for index, row in enumerate(rows) if row["id"] == current_id),
            0,
        )
        has_new_latest = bool(old_latest_id and rows and rows[0]["id"] != old_latest_id)
        if has_new_latest and current_index != 0 and self.isVisible():
            self._index = current_index
            self._next_index = 0
            self._progress = 0.0
            self._elapsed.start()
            self._animation_timer.start()
        else:
            self._index = 0
            self._next_index = None
            self._progress = 0.0
            self._animation_timer.stop()
        self.update()

    def message_count(self):
        return len(self._messages)

    def current_source_text(self):
        if not self._messages:
            return ""
        return self._messages[self._index]["text"]

    def current_display_text(self):
        return self._elide(self.current_source_text())

    def is_animating(self):
        return self._animation_timer.isActive()

    def content_width(self):
        return max(1, self.width() - 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)

    def hideEvent(self, event):
        self._animation_timer.stop()
        if self._next_index is not None:
            self._index = self._next_index
            self._next_index = None
            self._progress = 0.0
        super().hideEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setClipRect(self.rect().adjusted(8, 0, -8, 0))
        if not self._messages:
            return
        if self._next_index is None:
            self._draw_message(painter, self._index, 0, 1.0)
        else:
            distance = round(self.height() * self._progress)
            self._draw_message(painter, self._index, -distance, 1.0 - self._progress)
            self._draw_message(painter, self._next_index, self.height() - distance, self._progress)

    def _animate(self):
        self._progress = min(1.0, self._elapsed.elapsed() / self.ANIMATION_DURATION_MS)
        if self._progress >= 1.0:
            self._index = self._next_index
            self._next_index = None
            self._progress = 0.0
            self._animation_timer.stop()
        self.update()

    def _elide(self, text):
        return self.fontMetrics().elidedText(str(text or ""), Qt.ElideRight, self.content_width())

    def _draw_message(self, painter, index, y_offset, opacity):
        message = self._messages[index]
        metrics = self.fontMetrics()
        baseline = y_offset + (self.height() - metrics.height()) // 2 + metrics.ascent()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        painter.setPen(message["color"])
        painter.drawText(8, baseline, self._elide(message["text"]))
        painter.setOpacity(1.0)


class MiniNewsPanel(QWidget):
    MAX_ITEMS = 50
    EXPANDED_ITEMS = 4
    ROW_HEIGHT = 93
    HISTORY_SUMMARY_LIMIT = 96
    IDLE_HEIGHT = 44

    open_full_requested = Signal()
    pin_changed = Signal(bool)
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._items = []
        self._items_rendered = False
        self._important_only = False
        self._collapsed_items = 1
        self._background_alpha = 190
        self._expanded = False
        self._drag_offset = None
        self._pinned = None
        self._idle_height = self.IDLE_HEIGHT
        self._row_height = self.ROW_HEIGHT
        self._expanded_header_height = 46

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)

        self.header_widget = QWidget(self)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(6)
        self.title_label = QLabel("实时资讯")
        self.title_label.setObjectName("miniNewsTitle")
        self.status_label = QLabel("最新")
        self.status_label.setObjectName("miniNewsStatus")
        header.addWidget(self.title_label)
        header.addWidget(self.status_label)
        header.addStretch(1)
        self.expand_button = QPushButton("完整")
        self.expand_button.setObjectName("miniNewsButton")
        self.expand_button.clicked.connect(self.open_full_requested.emit)
        header.addWidget(self.expand_button)
        self.pin_button = QPushButton("置顶")
        self.pin_button.setObjectName("miniNewsPin")
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip("保持迷你资讯置顶")
        self.pin_button.toggled.connect(self.pin_changed.emit)
        header.addWidget(self.pin_button)
        root.addWidget(self.header_widget)

        self.ticker = RollingNewsLabel(self)
        self.ticker.activated.connect(self.open_full_requested.emit)
        root.addWidget(self.ticker)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("miniNewsList")
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.open_full_requested.emit())
        root.addWidget(self.list_widget)

        self.setStyleSheet("""
            QLabel#miniNewsTitle { color: #ffffff; font-weight: 600; }
            QLabel#miniNewsStatus { color: #aeb7c6; }
            QListWidget#miniNewsList { background: transparent; border: 0; outline: 0; color: #eef1f5; }
            QListWidget#miniNewsList::item { border-bottom: 1px solid rgba(255,255,255,28); padding: 5px 2px; }
            QScrollBar:vertical { background: transparent; width: 3px; margin: 2px 0; }
            QScrollBar::handle:vertical { background: rgba(190,198,210,105); min-height: 24px; border-radius: 1px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: transparent; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QPushButton#miniNewsButton, QPushButton#miniNewsPin { color: #d9dee8; background: rgba(255,255,255,18); border: 0; padding: 3px 7px; }
            QPushButton#miniNewsButton:hover, QPushButton#miniNewsPin:hover { background: rgba(255,255,255,40); }
            QPushButton#miniNewsPin:checked { color: #ffffff; background: rgba(75,125,255,120); }
        """)
        self._update_height()

    def apply_config(self, config):
        self._collapsed_items = 1
        opacity = max(20, min(100, int(config.get("mini_opacity", 75))))
        self._background_alpha = round(255 * opacity / 100)
        width = max(420, min(1280, int(config.get("mini_width", 840))))
        font_size = max(9, min(20, int(config.get("mini_font_size", 10))))
        font = QFont("Microsoft YaHei", font_size, QFont.Medium)
        self.setFixedWidth(width)
        self.setFont(font)
        self.ticker.setFont(font)
        self.list_widget.setFont(font)
        metrics = self.fontMetrics()
        self.ticker.setFixedHeight(max(28, metrics.height() + 8))
        self._idle_height = self.ticker.height() + 16
        self._row_height = max(self.ROW_HEIGHT, metrics.lineSpacing() * 3 + 18)
        self._expanded_header_height = max(46, metrics.height() + 24)
        for index in range(self.list_widget.count()):
            self.list_widget.item(index).setSizeHint(QSize(0, self._row_height))
        self.ticker.update()
        pinned = bool(config.get("mini_pinned", False))
        self.pin_button.blockSignals(True)
        self.pin_button.setChecked(pinned)
        self.pin_button.blockSignals(False)
        if self._pinned != pinned:
            geometry = self.geometry()
            visible = self.isVisible()
            self._pinned = pinned
            self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
            if visible:
                self.setGeometry(geometry)
                self.show()
        self._update_height()
        self.update()

    def set_items(self, items, important_only=False):
        rows = [dict(item) for item in items or [] if isinstance(item, dict) and item.get("id")]
        rows.sort(key=lambda item: int(item.get("timestamp") or 0), reverse=True)
        important_only = bool(important_only)
        if important_only:
            rows = [item for item in rows if item.get("important")]
        rows = rows[:self.MAX_ITEMS]
        if self._items_rendered and rows == self._items and important_only == self._important_only:
            return False
        self._items = rows
        self._important_only = important_only
        self._items_rendered = True
        ticker_rows = self._items or [None]
        self.ticker.set_messages([
            {
                "id": row.get("id") if row else "empty",
                "text": self._ticker_text(row) if row else "暂无符合条件的消息",
                "color": "#ff665e" if row and row.get("important") else "#eef1f5",
            }
            for row in ticker_rows
        ])
        self.list_widget.clear()
        for row in self._items:
            item = QListWidgetItem(self._item_text(row))
            item.setSizeHint(QSize(0, self._row_height))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            item.setForeground(QColor("#ff665e" if row.get("important") else "#eef1f5"))
            item.setToolTip(str(row.get("title") or ""))
            self.list_widget.addItem(item)
        if not self._items:
            empty = QListWidgetItem("暂无符合条件的消息")
            empty.setSizeHint(QSize(0, self._row_height))
            empty.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            empty.setForeground(QColor("#aeb7c6"))
            self.list_widget.addItem(empty)
        self.list_widget.scrollToTop()
        self.status_label.setText(self._latest_time())
        self._update_height()
        return True

    def items(self):
        return list(self._items)

    def is_expanded(self):
        return self._expanded

    def expand_view(self):
        if self._expanded:
            return
        self._expanded = True
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._update_height()

    def collapse_view(self):
        self._expanded = False
        self.list_widget.scrollToTop()
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        radius = 20 if not self._expanded else 7
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)
        super().paintEvent(event)

    def _update_height(self):
        if not self._expanded:
            self.header_widget.hide()
            self.list_widget.hide()
            self.ticker.show()
            self.setFixedHeight(self._idle_height)
            return
        self.ticker.hide()
        self.header_widget.show()
        self.list_widget.show()
        available = max(1, min(self.EXPANDED_ITEMS, max(1, self.list_widget.count())))
        self.list_widget.setFixedHeight(available * self._row_height + 2)
        self.setFixedHeight(self.list_widget.height() + self._expanded_header_height)

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
        for prefix in (f"【{title}】", title):
            if summary.startswith(prefix):
                summary = summary[len(prefix):].lstrip(" ：:，,")
                break
        first = f"{time_text}  {title}" if time_text else title
        if summary and summary != title:
            excerpt = summary[:MiniNewsPanel.HISTORY_SUMMARY_LIMIT].rstrip()
            if len(summary) > MiniNewsPanel.HISTORY_SUMMARY_LIMIT:
                excerpt += "…"
            return first + "\n" + excerpt
        return first

    @staticmethod
    def _ticker_text(item):
        if not isinstance(item, dict):
            return ""
        raw = str(item.get("published_at") or "")
        time_text = raw[11:16] if len(raw) >= 16 else raw[-5:]
        title = " ".join(str(item.get("title") or "财经快讯").split())
        summary = " ".join(str(item.get("summary") or "").split())
        for prefix in (f"【{title}】", title):
            if summary.startswith(prefix):
                summary = summary[len(prefix):].lstrip(" ：:，,")
                break
        parts = [part for part in (time_text, title, summary if summary != title else "") if part]
        return "  ·  ".join(parts)
