import ctypes
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class NewsPanel(QWidget):
    BATCH_SIZE = 15
    refresh_requested = Signal()
    important_only_changed = Signal(bool)
    mute_today_changed = Signal(bool)
    pin_changed = Signal(bool)
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("StockWidget 实时资讯")
        self.setFont(QFont("Microsoft YaHei", 10))
        self.setMinimumSize(460, 560)
        self.resize(540, 720)
        self._items = []
        self._visible_count = 0
        self._date_headings = []
        self._muted_today = False
        self._pinned = False
        self._display_limit = self.BATCH_SIZE
        self.load_more_button = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("newsHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 14)
        header_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("实时资讯")
        title.setObjectName("newsTitle")
        self.subtitle = QLabel("新浪财经 7×24")
        self.subtitle.setObjectName("newsSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(self.subtitle)
        title_row.addLayout(title_block)
        title_row.addStretch(1)
        self.pin_button = QPushButton("置顶")
        self.pin_button.setObjectName("quietButton")
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip("保持资讯窗口显示在其他窗口上方")
        self.pin_button.toggled.connect(self._on_pin_toggled)
        title_row.addWidget(self.pin_button)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("quietButton")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        title_row.addWidget(self.refresh_button)
        header_layout.addLayout(title_row)

        filter_row = QHBoxLayout()
        self.important_checkbox = QCheckBox("仅看重要")
        self.important_checkbox.toggled.connect(self._on_important_toggled)
        filter_row.addWidget(self.important_checkbox)
        filter_row.addStretch(1)
        self.mute_button = QPushButton("暂停今日弹出")
        self.mute_button.setObjectName("quietButton")
        self.mute_button.setCheckable(True)
        self.mute_button.setToolTip("仅停止今日新资讯自动展开，消息仍会继续更新")
        self.mute_button.toggled.connect(self._on_mute_toggled)
        filter_row.addWidget(self.mute_button)
        header_layout.addLayout(filter_row)
        root.addWidget(header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content.setObjectName("newsContent")
        self.timeline = QVBoxLayout(self.content)
        self.timeline.setContentsMargins(24, 18, 24, 28)
        self.timeline.setSpacing(0)
        self.timeline.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        self.setStyleSheet("""
            NewsPanel, QWidget#newsContent { background: #f7f8fa; color: #20242c; }
            QFrame#newsHeader { background: #ffffff; border-bottom: 1px solid #e5e8ee; }
            QLabel#newsTitle { color: #161a22; font-size: 20px; font-weight: 600; }
            QLabel#newsSubtitle { color: #7a8190; font-size: 12px; }
            QLabel#dateHeading { color: #4a5261; font-size: 13px; font-weight: 600; padding: 6px 0 10px 0; }
            QLabel#newsTime { color: #356ae6; font-size: 12px; font-weight: 600; min-width: 42px; }
            QLabel#newsItemTitle { color: #1f2430; font-size: 14px; font-weight: 600; }
            QLabel#newsSummary { color: #535b68; font-size: 13px; }
            QLabel#newsMeta { color: #9298a4; font-size: 11px; }
            QLabel#importantNewsTime, QLabel#importantNewsTitle, QLabel#importantNewsSummary { color: #d92d20; }
            QFrame#timelineLine { background: #d9e1f5; min-width: 1px; max-width: 1px; }
            QFrame#timelineDot { background: #4778ef; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px; }
            QFrame#importantTimelineLine { background: #f3c0bc; min-width: 1px; max-width: 1px; }
            QFrame#importantTimelineDot { background: #e5483f; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px; }
            QPushButton#quietButton { background: transparent; color: #5f6878; border: 1px solid #d9dde5; border-radius: 4px; padding: 5px 10px; }
            QPushButton#quietButton:hover { background: #f0f3f8; color: #263044; }
            QPushButton#quietButton:checked { background: #eaf0ff; color: #245bd7; border-color: #9bb4f2; }
            QPushButton#linkButton { background: transparent; color: #356ae6; border: 0; padding: 2px 0; text-align: left; }
            QCheckBox { color: #555d6b; spacing: 6px; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
            QScrollBar::handle:vertical { background: #c8ced9; border-radius: 4px; min-height: 32px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def items(self):
        return list(self._items)

    def visible_item_count(self):
        return self._visible_count

    def date_heading_count(self):
        return len(self._date_headings)

    def date_heading_texts(self):
        return list(self._date_headings)

    def set_items(self, items):
        valid = [dict(item) for item in items or [] if isinstance(item, dict) and item.get("id")]
        valid = sorted(valid, key=lambda item: int(item.get("timestamp") or 0), reverse=True)[:5000]
        if valid == self._items:
            return
        if not self._items:
            self._display_limit = self.BATCH_SIZE
        self._items = valid
        self._rebuild()

    def set_important_only(self, enabled):
        enabled = bool(enabled)
        if self.important_checkbox.isChecked() == enabled:
            return
        self.important_checkbox.blockSignals(True)
        self.important_checkbox.setChecked(enabled)
        self.important_checkbox.blockSignals(False)
        self._display_limit = self.BATCH_SIZE
        self._rebuild()

    def set_muted_today(self, muted):
        self._muted_today = bool(muted)
        self.mute_button.blockSignals(True)
        self.mute_button.setChecked(self._muted_today)
        self.mute_button.setText("恢复今日弹出" if self._muted_today else "暂停今日弹出")
        self.mute_button.blockSignals(False)

    def is_muted_today(self):
        return self._muted_today

    def set_pinned(self, pinned):
        pinned = bool(pinned)
        self.pin_button.blockSignals(True)
        self.pin_button.setChecked(pinned)
        self.pin_button.blockSignals(False)
        if self._pinned == pinned:
            return
        self._apply_pinned(pinned)

    def _apply_pinned(self, pinned):
        geometry = self.geometry()
        visible = self.isVisible()
        self._pinned = bool(pinned)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self._pinned)
        if visible:
            self.setGeometry(geometry)
            self.show()
            self.raise_()

    def _on_pin_toggled(self, pinned):
        self._apply_pinned(pinned)
        self.pin_changed.emit(bool(pinned))

    def _on_mute_toggled(self, muted):
        self._muted_today = bool(muted)
        self.mute_button.setText("恢复今日弹出" if self._muted_today else "暂停今日弹出")
        self.mute_today_changed.emit(self._muted_today)

    def set_source_name(self, source, cached_count=None):
        text = f"{str(source or '财经快讯')} 7×24"
        if cached_count is not None:
            text += f" · 本地三日 {max(0, int(cached_count))} 条"
        self.subtitle.setText(text)

    def show_news(self, auto_show=False, anchor=None):
        if auto_show and self._muted_today:
            return
        if not self.isVisible():
            target_screen = None
            if anchor is not None:
                target_screen = QApplication.screenAt(anchor.frameGeometry().center())
            target_screen = target_screen or QApplication.primaryScreen()
            screen = target_screen.availableGeometry()
            self.move(screen.right() - self.width() - 24, screen.top() + 48)
            self.show()
        if not auto_show:
            self._activate_manual()
            QTimer.singleShot(0, self._activate_manual)
        else:
            self.raise_()

    def _activate_manual(self):
        if not self.isVisible():
            return
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def _on_important_toggled(self, enabled):
        self._display_limit = self.BATCH_SIZE
        self._rebuild()
        self.important_only_changed.emit(bool(enabled))

    def _clear_timeline(self):
        self.load_more_button = None
        while self.timeline.count():
            item = self.timeline.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _date_and_time(item):
        raw = str(item.get("published_at") or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
            try:
                value = datetime.strptime(raw, fmt)
                if fmt.startswith("%H"):
                    return "今日", value.strftime("%H:%M")
                weekdays = "一二三四五六日"
                return value.strftime("%m月%d日") + f" 星期{weekdays[value.weekday()]}", value.strftime("%H:%M")
            except ValueError:
                continue
        return "最新消息", raw[-5:] if raw else "--:--"

    def _rebuild(self):
        self._clear_timeline()
        important_only = self.important_checkbox.isChecked()
        visible = [item for item in self._items if not important_only or item.get("important")]
        rendered = visible[:self._display_limit]
        self._visible_count = len(rendered)
        self._date_headings = []
        last_date = None
        if not visible:
            empty = QLabel("暂无符合条件的消息")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #9097a3; padding: 80px 0;")
            self.timeline.addWidget(empty)
            self.timeline.addStretch(1)
            return
        for item in rendered:
            date_text, time_text = self._date_and_time(item)
            if date_text != last_date:
                heading = QLabel(date_text)
                heading.setObjectName("dateHeading")
                self.timeline.addWidget(heading)
                self._date_headings.append(date_text)
                last_date = date_text
            self.timeline.addWidget(self._create_item(item, time_text))
        self.load_more_button = QPushButton(f"加载更多（剩余 {len(visible) - len(rendered)} 条）")
        self.load_more_button.setObjectName("quietButton")
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setVisible(len(rendered) < len(visible))
        self.timeline.addWidget(self.load_more_button, 0, Qt.AlignHCenter)
        self.timeline.addStretch(1)

    def _load_more(self):
        self._display_limit += self.BATCH_SIZE
        self._rebuild()

    def _create_item(self, item, time_text):
        important = bool(item.get("important"))
        row = QWidget(self.content)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(10)

        rail = QVBoxLayout()
        rail.setContentsMargins(0, 4, 0, 0)
        rail.setSpacing(0)
        dot = QFrame(row)
        dot.setObjectName("importantTimelineDot" if important else "timelineDot")
        line = QFrame(row)
        line.setObjectName("importantTimelineLine" if important else "timelineLine")
        rail.addWidget(dot, 0, Qt.AlignHCenter)
        rail.addWidget(line, 1, Qt.AlignHCenter)
        layout.addLayout(rail)

        body = QVBoxLayout()
        body.setSpacing(5)
        time_label = QLabel(time_text)
        time_label.setObjectName("importantNewsTime" if important else "newsTime")
        body.addWidget(time_label)
        title = QLabel(str(item.get("title") or "财经快讯"))
        title.setObjectName("importantNewsTitle" if important else "newsItemTitle")
        title.setWordWrap(True)
        body.addWidget(title)
        summary_text = str(item.get("summary") or "").strip()
        if summary_text:
            if len(summary_text) > 500:
                summary_text = summary_text[:500].rstrip() + "…"
            summary = QLabel(summary_text)
            summary.setObjectName("importantNewsSummary" if important else "newsSummary")
            summary.setWordWrap(True)
            summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body.addWidget(summary)
        meta_parts = [str(item.get("source") or "").strip(), str(item.get("category") or "").strip()]
        meta = QLabel(" · ".join(part for part in meta_parts if part))
        meta.setObjectName("newsMeta")
        body.addWidget(meta)
        url = str(item.get("url") or "").strip()
        if url.lower().startswith(("http://", "https://")):
            link = QPushButton("查看原文")
            link.setObjectName("linkButton")
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            body.addWidget(link, 0, Qt.AlignLeft)
        layout.addLayout(body, 1)
        return row
