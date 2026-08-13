from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPainterPath, QPen
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


class IntradayLineChartWidget(QWidget):
    UP_COLOR = QColor("#ef5350")
    DOWN_COLOR = QColor("#2fb171")
    NEUTRAL_COLOR = QColor("#c9ced6")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self._prev_close = 0.0
        self._status_text = "正在加载当日分时数据..."
        self._hover_index = None
        self.setMinimumSize(620, 320)
        self.setMouseTracking(True)

    @property
    def points(self):
        return list(self._points)

    @staticmethod
    def _normalize_payload(payload):
        points = []
        if not isinstance(payload, dict):
            return points, 0.0
        for item in payload.get("points") or []:
            if not isinstance(item, dict):
                continue
            try:
                minute = int(item.get("minute"))
                price = float(item.get("price"))
            except (TypeError, ValueError):
                continue
            if 0 <= minute <= 241 and price > 0:
                points.append({"minute": minute, "price": price})
        points.sort(key=lambda item: item["minute"])
        deduped = []
        for item in points:
            if deduped and deduped[-1]["minute"] == item["minute"]:
                deduped[-1] = item
            else:
                deduped.append(item)
        try:
            prev_close = float(payload.get("prev_close") or 0.0)
        except (TypeError, ValueError):
            prev_close = 0.0
        return deduped, prev_close

    def set_payload(self, payload, status_text=""):
        self._points, self._prev_close = self._normalize_payload(payload)
        self._status_text = str(status_text or "").strip()
        if not self._points and not self._status_text:
            self._status_text = "暂无可用分时数据"
        self._hover_index = None
        self.update()

    def _plot_rect(self):
        return QRectF(54.0, 34.0, max(1.0, self.width() - 94.0), max(1.0, self.height() - 78.0))

    def _price_bounds(self):
        prices = [point["price"] for point in self._points]
        if self._prev_close > 0:
            prices.append(self._prev_close)
        if not prices:
            return 0.0, 1.0
        low_price = min(prices)
        high_price = max(prices)
        if high_price <= low_price:
            padding = max(abs(high_price) * 0.002, 0.001)
        else:
            padding = max((high_price - low_price) * 0.08, abs(high_price) * 0.001, 0.001)
        return low_price - padding, high_price + padding

    def _x_for_minute(self, minute, plot):
        return plot.left() + max(0.0, min(241.0, float(minute))) / 241.0 * plot.width()

    @staticmethod
    def _minute_label(minute):
        try:
            minute = int(minute)
        except Exception:
            return ""
        if minute <= 120:
            total = 9 * 60 + 30 + minute
        else:
            total = 13 * 60 + minute - 121
        return f"{total // 60:02d}:{total % 60:02d}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#17191d"))

        if not self._points:
            painter.setPen(QColor("#aeb4bd"))
            empty_font = QFont(self.font())
            empty_font.setPointSize(11)
            painter.setFont(empty_font)
            painter.drawText(self.rect(), Qt.AlignCenter, self._status_text or "暂无可用分时数据")
            return

        plot = self._plot_rect()
        low_price, high_price = self._price_bounds()
        latest = self._points[-1]["price"]
        line_color = self.NEUTRAL_COLOR
        if self._prev_close > 0:
            if latest > self._prev_close:
                line_color = self.UP_COLOR
            elif latest < self._prev_close:
                line_color = self.DOWN_COLOR

        grid_pen = QPen(QColor("#30343b"), 1)
        text_color = QColor("#9da5b0")
        axis_pen = QPen(QColor("#4c535e"), 1)

        chart_font = QFont(self.font())
        chart_font.setPointSize(9)
        painter.setFont(chart_font)

        for step in range(5):
            ratio = step / 4.0
            y = plot.top() + ratio * plot.height()
            price = high_price - ratio * (high_price - low_price)
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text_color)
            painter.drawText(QRectF(plot.right() + 6.0, y - 9.0, 52.0, 18.0), Qt.AlignLeft | Qt.AlignVCenter, f"{price:.2f}")

        for minute, label in ((0, "09:30"), (120, "11:30"), (121, "13:00"), (241, "15:00")):
            x = self._x_for_minute(minute, plot)
            painter.setPen(grid_pen if minute not in (0, 241) else axis_pen)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(text_color)
            painter.drawText(QRectF(x - 24.0, plot.bottom() + 8.0, 48.0, 18.0), Qt.AlignCenter, label)

        painter.setPen(axis_pen)
        painter.drawRect(plot)

        if self._prev_close > 0:
            y_prev = KLineChartWidget.price_to_y(self._prev_close, plot.top(), plot.bottom(), low_price, high_price)
            prev_col = QColor("#8a929e")
            prev_col.setAlpha(150)
            painter.setPen(QPen(prev_col, 1, Qt.DashLine))
            painter.drawLine(QPointF(plot.left(), y_prev), QPointF(plot.right(), y_prev))

        path = QPainterPath()
        for index, point in enumerate(self._points):
            chart_point = QPointF(
                self._x_for_minute(point["minute"], plot),
                KLineChartWidget.price_to_y(point["price"], plot.top(), plot.bottom(), low_price, high_price),
            )
            if index == 0:
                path.moveTo(chart_point)
            else:
                path.lineTo(chart_point)

        fill_color = QColor(line_color)
        fill_color.setAlpha(32)
        fill = QPainterPath(path)
        fill.lineTo(QPointF(self._x_for_minute(self._points[-1]["minute"], plot), plot.bottom()))
        fill.lineTo(QPointF(self._x_for_minute(self._points[0]["minute"], plot), plot.bottom()))
        fill.closeSubpath()
        painter.fillPath(fill, QBrush(fill_color))

        painter.setPen(QPen(line_color, 1.7))
        painter.drawPath(path)

        painter.setPen(QColor("#e2e6ec"))
        change_text = ""
        if self._prev_close > 0:
            change_pct = (latest / self._prev_close - 1) * 100.0
            change_text = f"  {change_pct:+.2f}%"
        painter.drawText(QRectF(plot.left(), 8.0, plot.width(), 22.0), Qt.AlignLeft | Qt.AlignVCenter, f"最新 {latest:.2f}{change_text}")

        if self._hover_index is not None and 0 <= self._hover_index < len(self._points):
            point = self._points[self._hover_index]
            x = self._x_for_minute(point["minute"], plot)
            y = KLineChartWidget.price_to_y(point["price"], plot.top(), plot.bottom(), low_price, high_price)
            painter.setPen(QPen(QColor("#8a929e"), 1, Qt.DashLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#e2e6ec"))
            detail = f"{self._minute_label(point['minute'])}  {point['price']:.2f}"
            painter.drawText(QRectF(plot.left() + 150.0, 8.0, plot.width() - 150.0, 22.0), Qt.AlignRight | Qt.AlignVCenter, detail)

    def mouseMoveEvent(self, event):
        if not self._points:
            return
        plot = self._plot_rect()
        if not plot.contains(event.position()):
            self._hover_index = None
        else:
            minute = (event.position().x() - plot.left()) / max(1.0, plot.width()) * 241.0
            self._hover_index = min(
                range(len(self._points)),
                key=lambda idx: abs(self._points[idx]["minute"] - minute),
            )
        self.update()

    def leaveEvent(self, event):
        self._hover_index = None
        self.update()
        super().leaveEvent(event)


class IntradayLineChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.code = ""
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(680, 400)
        self.resize(760, 460)
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
        self.detail_label = QLabel("分时 · 当日")
        self.detail_label.setStyleSheet("color: #9da5b0;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.detail_label)
        layout.addLayout(header)

        self.chart = IntradayLineChartWidget(self)
        layout.addWidget(self.chart, 1)

    def show_stock(self, code, name, payload=None, status_text=""):
        self.code = str(code or "")
        display_name = str(name or self.code)
        self.setWindowTitle(f"{display_name} {self.code} 分时")
        self.title_label.setText(f"{display_name}  {self.code}")
        self.chart.set_payload(payload or {}, status_text=status_text)
        self.show()
        self.raise_()
        self.activateWindow()


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
