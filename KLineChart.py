from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class KLineChartWidget(QWidget):
    UP_COLOR = QColor("#ef5350")
    DOWN_COLOR = QColor("#2fb171")
    NEUTRAL_COLOR = QColor("#c9ced6")
    MA_COLORS = {
        5: QColor("#f4c542"),
        10: QColor("#42b8d4"),
        20: QColor("#b58ae8"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._status_text = "正在加载日线数据..."
        self._hover_index = None
        self.setMinimumSize(680, 360)
        self.setMouseTracking(True)

    @property
    def rows(self):
        return list(self._rows)

    @staticmethod
    def price_to_y(price, top, bottom, low_price, high_price):
        if high_price <= low_price:
            return (float(top) + float(bottom)) / 2.0
        ratio = (float(price) - float(low_price)) / (float(high_price) - float(low_price))
        return float(bottom) - ratio * (float(bottom) - float(top))

    @staticmethod
    def _normalize_rows(rows):
        normalized = []
        for raw in rows or []:
            if not isinstance(raw, dict):
                continue
            try:
                opening = float(raw.get("open") or 0.0)
                close = float(raw.get("close") or 0.0)
                high = float(raw.get("high") or 0.0)
                low = float(raw.get("low") or 0.0)
            except (TypeError, ValueError):
                continue
            if min(opening, close, high, low) <= 0:
                continue
            try:
                volume = float(raw.get("volume") or 0.0)
            except (TypeError, ValueError):
                volume = 0.0
            normalized.append({
                "date": str(raw.get("date") or ""),
                "open": opening,
                "close": close,
                "high": max(high, opening, close),
                "low": min(low, opening, close),
                "volume": volume,
                "realtime": bool(raw.get("realtime")),
            })
        normalized.sort(key=lambda item: item["date"])
        return normalized[-60:]

    def set_rows(self, rows, status_text=""):
        self._rows = self._normalize_rows(rows)
        self._status_text = str(status_text or "").strip()
        if not self._rows and not self._status_text:
            self._status_text = "暂无可用日线数据"
        self._hover_index = None
        self.update()

    def _moving_average(self, period):
        values = []
        closes = [row["close"] for row in self._rows]
        for index in range(len(closes)):
            if index + 1 < period:
                values.append(None)
                continue
            window = closes[index + 1 - period:index + 1]
            values.append(sum(window) / float(period))
        return values

    def _price_bounds(self):
        if not self._rows:
            return 0.0, 1.0
        low_price = min(row["low"] for row in self._rows)
        high_price = max(row["high"] for row in self._rows)
        spread = high_price - low_price
        padding = max(spread * 0.08, abs(high_price) * 0.002, 0.001)
        return low_price - padding, high_price + padding

    @staticmethod
    def _price_decimals(high_price):
        return 3 if high_price < 10 else 2

    def _plot_rect(self):
        return QRectF(56.0, 42.0, max(80.0, self.width() - 124.0), max(80.0, self.height() - 94.0))

    def _x_for_index(self, index, plot):
        count = max(1, len(self._rows))
        return plot.left() + (float(index) + 0.5) * plot.width() / float(count)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#17191d"))

        if not self._rows:
            painter.setPen(QColor("#aeb4bd"))
            empty_font = QFont(self.font())
            empty_font.setPointSize(10)
            painter.setFont(empty_font)
            painter.drawText(self.rect(), Qt.AlignCenter, self._status_text or "暂无可用日线数据")
            return

        plot = self._plot_rect()
        low_price, high_price = self._price_bounds()
        decimals = self._price_decimals(high_price)
        grid_pen = QPen(QColor("#343942"), 1, Qt.DotLine)
        axis_pen = QPen(QColor("#6b727d"), 1)
        text_color = QColor("#b9c0ca")

        chart_font = QFont(self.font())
        chart_font.setPointSize(8)
        painter.setFont(chart_font)
        for tick in range(5):
            ratio = tick / 4.0
            y = plot.top() + ratio * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            value = high_price - ratio * (high_price - low_price)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(plot.right() + 8.0, y - 9.0, 58.0, 18.0),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{value:.{decimals}f}",
            )

        painter.setPen(axis_pen)
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.topRight(), plot.bottomRight())

        count = len(self._rows)
        tick_indexes = sorted({0, count - 1, *(round(i * (count - 1) / 4.0) for i in range(1, 4))})
        for index in tick_indexes:
            x = self._x_for_index(index, plot)
            date_text = self._rows[index]["date"]
            if len(date_text) >= 10:
                date_text = date_text[5:10]
            painter.setPen(text_color)
            painter.drawText(QRectF(x - 28.0, plot.bottom() + 7.0, 56.0, 18.0), Qt.AlignCenter, date_text)

        slot_width = plot.width() / float(max(1, count))
        body_width = max(3.0, min(9.0, slot_width * 0.58))
        for index, row in enumerate(self._rows):
            x = self._x_for_index(index, plot)
            high_y = self.price_to_y(row["high"], plot.top(), plot.bottom(), low_price, high_price)
            low_y = self.price_to_y(row["low"], plot.top(), plot.bottom(), low_price, high_price)
            open_y = self.price_to_y(row["open"], plot.top(), plot.bottom(), low_price, high_price)
            close_y = self.price_to_y(row["close"], plot.top(), plot.bottom(), low_price, high_price)
            color = self.UP_COLOR if row["close"] > row["open"] else self.DOWN_COLOR
            if row["close"] == row["open"]:
                color = self.NEUTRAL_COLOR
            painter.setPen(QPen(color, 1.0))
            painter.drawLine(QPointF(x, high_y), QPointF(x, low_y))
            body_top = min(open_y, close_y)
            body_height = max(1.5, abs(open_y - close_y))
            body = QRectF(x - body_width / 2.0, body_top, body_width, body_height)
            if row["close"] >= row["open"]:
                painter.drawRect(body)
            else:
                painter.fillRect(body, color)

        legend_x = plot.left()
        for period in (5, 10, 20):
            values = self._moving_average(period)
            path = QPainterPath()
            started = False
            for index, value in enumerate(values):
                if value is None:
                    continue
                point = QPointF(
                    self._x_for_index(index, plot),
                    self.price_to_y(value, plot.top(), plot.bottom(), low_price, high_price),
                )
                if not started:
                    path.moveTo(point)
                    started = True
                else:
                    path.lineTo(point)
            painter.setPen(QPen(self.MA_COLORS[period], 1.35))
            if started:
                painter.drawPath(path)
            painter.drawText(QRectF(legend_x, 12.0, 58.0, 20.0), Qt.AlignLeft | Qt.AlignVCenter, f"MA{period}")
            legend_x += 58.0

        if self._hover_index is not None and 0 <= self._hover_index < count:
            index = self._hover_index
            row = self._rows[index]
            x = self._x_for_index(index, plot)
            painter.setPen(QPen(QColor("#8a929e"), 1, Qt.DashLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            detail = (
                f"{row['date']}  开 {row['open']:.{decimals}f}  高 {row['high']:.{decimals}f}  "
                f"低 {row['low']:.{decimals}f}  收 {row['close']:.{decimals}f}"
            )
            painter.setPen(QColor("#e2e6ec"))
            painter.drawText(QRectF(plot.left() + 188.0, 10.0, plot.width() - 188.0, 22.0), Qt.AlignRight | Qt.AlignVCenter, detail)

    def mouseMoveEvent(self, event):
        if not self._rows:
            return
        plot = self._plot_rect()
        if not plot.contains(event.position()):
            self._hover_index = None
        else:
            relative = (event.position().x() - plot.left()) / max(1.0, plot.width())
            self._hover_index = max(0, min(len(self._rows) - 1, int(relative * len(self._rows))))
        self.update()

    def leaveEvent(self, event):
        self._hover_index = None
        self.update()
        super().leaveEvent(event)


class KLineChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.code = ""
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(720, 440)
        self.resize(800, 500)
        self.setStyleSheet("QDialog { background: #17191d; color: #e2e6ec; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel("")
        title_font = QFont(self.font())
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #e2e6ec;")
        self.detail_label = QLabel("日K · 前复权 · 最近60个交易日")
        self.detail_label.setStyleSheet("color: #9da5b0;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.detail_label)
        layout.addLayout(header)

        self.chart = KLineChartWidget(self)
        layout.addWidget(self.chart, 1)

    def show_stock(self, code, name, rows, status_text=""):
        self.code = str(code or "")
        display_name = str(name or self.code)
        self.setWindowTitle(f"{display_name} {self.code} 日K")
        self.title_label.setText(f"{display_name}  {self.code}")
        self.chart.set_rows(rows, status_text=status_text)
        self.show()
        self.raise_()
        self.activateWindow()
