from PySide6.QtCore import Qt, QRect, QPoint, QPointF, QAbstractTableModel, QModelIndex, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QToolTip

# ----- 颜色配置 -----
UP_COLOR = QColor("#dd2100")
DOWN_COLOR = QColor("#019933")
NEUTRAL_COLOR = QColor("#494949")

class SimpleTableModel(QAbstractTableModel):
    """
    主浮窗表格数据与格式
    """
    def __init__(self, rows=None, headers=None, align_right_cols=None, parent=None):
        super().__init__(parent)
        self._rows = rows or []
        self._headers = headers or []
        self._align_right = align_right_cols or []
        self.default_color = False
        self.fg_color = QColor("#FFFFFF")
        self._row_meta = []
        self._header_notes = {}

    def set_color_scheme(self, default: bool, fg: QColor):
        self.default_color = bool(default)
        self.fg_color = QColor(fg)

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self._rows[0]) if self._rows else len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        cell = "" if c >= len(self._rows[r]) else self._rows[r][c]

        if role == Qt.UserRole:
            if isinstance(cell, dict) and "k" in cell:
                return cell["k"]
            return None

        if role == Qt.UserRole + 1:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            return meta.get("price_alerts") or []

        if role == Qt.UserRole + 2:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            alerts = meta.get("price_alerts") or []
            if not alerts:
                return ""
            return "\n\n".join(str(a.get("detail", "")) for a in alerts if a.get("detail"))

        if role == Qt.ToolTipRole:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            note = str(meta.get("stock_note") or "").strip()
            return f"备注：{note}" if note else None

        if role == Qt.DisplayRole:
            return "" if isinstance(cell, dict) else str(cell)

        if role == Qt.TextAlignmentRole:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            row_type = meta.get("row_type")
            if row_type == "warning":
                return Qt.AlignCenter
            if row_type in ("group", "alert", "separator"):
                return Qt.AlignLeft | Qt.AlignVCenter
            return (Qt.AlignRight | Qt.AlignVCenter) if c in self._align_right else (Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ForegroundRole:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            row_type = meta.get("row_type")
            header = self._headers[c] if 0 <= c < len(self._headers) else ""
            if row_type == "group":
                c = QColor(self.fg_color)
                c.setAlpha(210)
                return c
            if row_type == "alert":
                return UP_COLOR if meta.get("triggered") else self.fg_color
            if row_type == "warning":
                c = QColor("#f0c36a")
                return c
            if row_type == "separator":
                c = QColor(self.fg_color)
                c.setAlpha(0)
                return c
            if header in ("名称", "代码"):
                note_color = QColor(str(meta.get("stock_note_color") or ""))
                if note_color.isValid():
                    return note_color
            if meta.get("strategy"):
                if header == "策略状态":
                    if meta.get("severity") == "danger":
                        return UP_COLOR
                    if meta.get("severity") == "warning":
                        return QColor("#f0c36a")
                    return self.fg_color

            if not self.default_color:
                return self.fg_color

            sign = 0
            if header in ("涨跌值", "涨跌幅", "现价"):
                sign = int(meta.get("delta", 0))
            elif header == "委比":
                sign = int(meta.get("commi", 0))
            elif header == "均价":
                sign = int(meta.get("avg", 0))
            elif header == "买一":
                sign = int(meta.get("b1", 0))
            elif header == "卖一":
                sign = int(meta.get("s1", 0))
            else:
                return self.fg_color

            if sign > 0:
                return UP_COLOR
            if sign < 0:
                return DOWN_COLOR
            return NEUTRAL_COLOR

        if role == Qt.FontRole:
            meta = self._row_meta[r] if 0 <= r < len(self._row_meta) else {}
            if meta.get("row_type") in ("group", "alert", "warning"):
                font = QFont()
                font.setBold(meta.get("row_type") == "group")
                return font

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self._headers):
            header = self._headers[section]
            note = str(self._header_notes.get(section, "") or "").strip()
            return f"{header} {note}" if note else header
        return None

    def set_rows_headers(self, rows, headers, meta=None, header_notes=None):
        self.beginResetModel()
        self._rows = rows or []
        self._headers = headers or []
        self._row_meta = list(meta or [{} for _ in self._rows])
        self._header_notes = dict(header_notes or {})
        self.endResetModel()

    def set_align_right_cols(self, cols_idx):
        self._align_right = set(cols_idx or [])


class PriceAlertNameDelegate(QStyledItemDelegate):
    """
    在名称列文字右侧绘制一个小圆圈感叹号，并只在图标区域显示提醒详情。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fg = QColor("#FFFFFF")

    def update_scheme(self, fg: QColor):
        self.fg = QColor(fg)

    def _icon_rect(self, option, index):
        alerts = index.data(Qt.UserRole + 1) or []
        if not alerts:
            return QRect()
        text = index.data(Qt.DisplayRole) or ""
        fm = option.fontMetrics
        size = max(9, min(14, fm.height() - 2))
        x = option.rect.left() + 4 + fm.horizontalAdvance(str(text)) + 5
        max_x = option.rect.right() - size - 2
        x = min(x, max_x)
        y = option.rect.top() + (option.rect.height() - size) // 2
        return QRect(x, y, size, size)

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        rect = self._icon_rect(option, index)
        if rect.isNull() or rect.width() <= 0:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        alerts = index.data(Qt.UserRole + 1) or []
        has_triggered = any(bool(a.get("triggered")) for a in alerts if isinstance(a, dict))
        color = QColor("#f0c36a") if has_triggered else QColor(self.fg)
        if not has_triggered:
            color.setAlpha(150)
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))
        font = QFont(option.font)
        font.setBold(True)
        font.setPointSize(max(7, option.font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, "!")
        painter.restore()

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip:
            detail = index.data(Qt.UserRole + 2)
            rect = self._icon_rect(option, index)
            if detail and rect.contains(event.pos()):
                pos = event.globalPos() + QPoint(14, 18)
                if view is not None and view.viewport() is not None:
                    pos = view.viewport().mapToGlobal(rect.bottomRight() + QPoint(10, 8))
                try:
                    owner = view.window() if view is not None else None
                    if owner is not None and hasattr(owner, "suspend_keep_top"):
                        owner.suspend_keep_top(6.0)
                except Exception:
                    pass
                QToolTip.showText(pos, detail, None)
                return True
            QToolTip.hideText()
            return False
        return super().helpEvent(event, view, option, index)


class KLineDelegate(QStyledItemDelegate):
    """
    当日K线图，基于昨收，今开，最高，最低，实时价
    """
    def __init__(self, parent=None, base_pt=12):
        super().__init__(parent)
        self.default_color = False
        self.fg = QColor("#FFFFFF")
        self.base_pt = max(1, int(base_pt))
        self.scale = 1.0  # 缩放

    def update_scheme(self, default_color: bool, fg: QColor):
        self.default_color = bool(default_color)
        self.fg = QColor(fg)

    def set_point_size(self, pt: int):
        self.scale = max(0.5, min(1.5, float(pt) / float(self.base_pt)))

    @staticmethod
    def _legacy_tuple(payload):
        if isinstance(payload, tuple) and len(payload) == 5:
            return payload
        if isinstance(payload, dict):
            ohlc = payload.get("ohlc")
            if isinstance(ohlc, tuple) and len(ohlc) == 5:
                return ohlc
        return None

    @staticmethod
    def _trend_points(payload):
        if not isinstance(payload, dict):
            return []
        points = []
        for item in payload.get("points") or []:
            if not isinstance(item, dict):
                continue
            try:
                minute = int(item.get("minute"))
                price = float(item.get("price"))
            except Exception:
                continue
            if minute < 0 or price <= 0:
                continue
            points.append({"minute": minute, "price": price})
        points.sort(key=lambda item: item["minute"])
        deduped = []
        for item in points:
            if deduped and deduped[-1]["minute"] == item["minute"]:
                deduped[-1] = item
            else:
                deduped.append(item)
        return deduped

    def _paint_intraday(self, painter: QPainter, option, payload):
        points = self._trend_points(payload)
        if len(points) < 2:
            return False

        try:
            prev_close = float(payload.get("prev_close") or 0.0)
        except Exception:
            prev_close = 0.0
        prices = [item["price"] for item in points]
        if prev_close > 0:
            prices.append(prev_close)
        low_price = min(prices)
        high_price = max(prices)
        if high_price <= low_price:
            padding = max(abs(high_price) * 0.002, 0.001)
            low_price -= padding
            high_price += padding
        else:
            padding = max((high_price - low_price) * 0.08, abs(high_price) * 0.001, 0.001)
            low_price -= padding
            high_price += padding

        cell = option.rect
        rect = cell.adjusted(3, 2, -3, -2)
        if rect.width() < 8 or rect.height() < 6:
            return True

        def y_for(price):
            ratio = (float(price) - low_price) / (high_price - low_price)
            return rect.bottom() - ratio * rect.height()

        def x_for_index(index):
            if len(points) <= 1:
                ratio = 0.5
            else:
                ratio = float(index) / float(len(points) - 1)
            return rect.left() + ratio * rect.width()

        latest = points[-1]["price"]
        line_color = QColor(self.fg)
        if self.default_color and prev_close > 0:
            if latest > prev_close:
                line_color = UP_COLOR
            elif latest < prev_close:
                line_color = DOWN_COLOR
            else:
                line_color = NEUTRAL_COLOR

        painter.save()
        painter.setClipRect(cell)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if prev_close > 0:
            dash_col = QColor(NEUTRAL_COLOR if self.default_color else self.fg)
            dash_col.setAlpha(95)
            y_prev = y_for(prev_close)
            painter.setPen(QPen(dash_col, 1, Qt.DashLine))
            painter.drawLine(QPointF(rect.left(), y_prev), QPointF(rect.right(), y_prev))

        path = QPainterPath()
        for index, item in enumerate(points):
            point = QPointF(x_for_index(index), y_for(item["price"]))
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        fill_color = QColor(line_color)
        fill_color.setAlpha(34 if self.default_color else 24)
        fill = QPainterPath(path)
        fill.lineTo(QPointF(rect.right(), rect.bottom()))
        fill.lineTo(QPointF(rect.left(), rect.bottom()))
        fill.closeSubpath()
        painter.fillPath(fill, QBrush(fill_color))

        painter.setPen(QPen(line_color, 1.6))
        painter.drawPath(path)
        painter.restore()
        return True

    def paint(self, painter: QPainter, option, index):
        k = index.data(Qt.UserRole)
        if self._paint_intraday(painter, option, k):
            return

        legacy = self._legacy_tuple(k)
        if not legacy:
            super().paint(painter, option, index)
            return

        o, c, h, l, p = legacy
        if h < l: h, l = l, h

        cell = option.rect
        rect = cell.adjusted(3, 2, -3, -2)

        sc = max(0.5, min(1.5, self.scale))
        vpad = max(2, int(rect.height() * 0.08))
        h_eff = max(6, rect.height() - 2 * vpad)
        krect = QRect(rect.left(), rect.top() + vpad, rect.width(), h_eff)

        low_bound = min(o, c, h, l, p)
        high_bound = max(o, c, h, l, p)
        if high_bound <= low_bound:
            pad = max(abs(high_bound) * 0.002, 0.001)
        else:
            pad = max((high_bound - low_bound) * 0.08, abs(high_bound) * 0.001, 0.001)
        low_bound -= pad
        high_bound += pad

        def y_for(v):
            y = (v - low_bound) / (high_bound - low_bound)
            return krect.top() + (1 - y) * krect.height()

        y_o, y_c, y_h, y_l, y_p = (y_for(o), y_for(c), y_for(h), y_for(l), y_for(p))

        painter.save()
        painter.setClipRect(cell)
        painter.setRenderHint(QPainter.Antialiasing, True)

        body_w = max(8, min(int(krect.width() * 0.34 * sc), 18))
        x = krect.center().x()

        # 昨收虚线
        dash_col = QColor(NEUTRAL_COLOR if self.default_color else self.fg)
        dash_col.setAlpha(120)
        painter.setPen(QPen(dash_col, 1, Qt.DashLine))
        painter.drawLine(QPointF(krect.left(), y_p), QPointF(krect.right(), y_p))

        kcolor = self.fg
        if self.default_color:
            if c>o:
                kcolor = UP_COLOR
            elif c<o:
                kcolor = DOWN_COLOR
            else:
                kcolor = NEUTRAL_COLOR

        top, bot = min(y_o, y_c), max(y_o, y_c)
        body_h = max(3, bot - top)
        body_x = x - body_w // 2

        painter.setPen(QPen(kcolor, 1.4))
        if c != o:
            # 实体
            painter.drawRect(body_x, top, body_w, body_h)
        else:
            # 一字实体
            painter.setPen(QPen(kcolor, 1.8))
            painter.drawLine(QPointF(body_x, y_c), QPointF(body_x + body_w, y_c))
            painter.setPen(QPen(kcolor, 1.4))
        if y_h < top:
            # 上影线
            painter.drawLine(QPointF(x, y_h), QPointF(x, top))
        if y_l > bot:
            # 下影线
            painter.drawLine(QPointF(x, bot), QPointF(x, y_l))
        if c < o: 
            # 填充实体（空阳线）
            painter.fillRect(body_x, top, body_w, body_h, QBrush(kcolor))

        painter.restore()
