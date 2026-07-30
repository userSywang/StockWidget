from PySide6.QtCore import Qt, QRect, QPoint, QAbstractTableModel, QModelIndex, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
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

            if not self.default_color:
                return self.fg_color

            header = self._headers[c] if 0 <= c < len(self._headers) else ""
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
            return self._headers[section]
        return None

    def set_rows_headers(self, rows, headers, meta=None):
        self.beginResetModel()
        self._rows = rows or []
        self._headers = headers or []
        self._row_meta = list(meta or [{} for _ in self._rows])
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

    def paint(self, painter: QPainter, option, index):
        k = index.data(Qt.UserRole)
        if not k or not isinstance(k, tuple) or len(k) != 5:
            super().paint(painter, option, index)
            return

        o, c, h, l, p = k
        if h < l: h, l = l, h

        cell = option.rect
        rect = cell.adjusted(2, 2, -2, -2)

        sc = max(0.5, min(1.5, self.scale))
        vpad = max(2, int(rect.height() * (0.12 + 0.06 * (sc - 1))))   # ~12%~18%
        h_eff = max(2, rect.height() - 2 * vpad)
        krect = QRect(rect.left(), rect.top() + vpad, rect.width(), h_eff)

        def y_for(v):
            if h == l == p:
                y = 0.5
            else:
                y = (v - min(l,p)) / (max(h,p) - min(l,p))
            return krect.top() + (1 - y) * krect.height()

        y_o, y_c, y_h, y_l, y_p = (y_for(o), y_for(c), y_for(h), y_for(l), y_for(p))

        painter.save()
        painter.setClipRect(cell)
        painter.setRenderHint(QPainter.Antialiasing, True)

        body_w = max(5, min(int(krect.width() * 0.4 * sc), 10))
        x = krect.center().x()

        # 昨收虚线
        dash_col = QColor(NEUTRAL_COLOR if self.default_color else self.fg)
        dash_col.setAlpha(180)
        painter.setPen(QPen(dash_col, 1, Qt.DashLine))
        painter.drawLine(x - body_w, y_p, x + body_w, y_p)

        kcolor = self.fg
        if self.default_color:
            if c>o:
                kcolor = UP_COLOR
            elif c<o:
                kcolor = DOWN_COLOR
            else:
                kcolor = NEUTRAL_COLOR

        top, bot = min(y_o, y_c), max(y_o, y_c)
        body_h = max(2, bot - top)
        body_x = x - body_w // 2

        painter.setPen(QPen(kcolor, 1))
        if c != o:
            # 实体
            painter.drawRect(body_x, top, body_w, body_h)
        else:
            # 一字实体
            painter.drawLine(body_x, y_c, body_x+body_w, y_c)
        if y_h < top:
            # 上影线
            painter.drawLine(x, y_h, x, top)
        if y_l > bot:
            # 下影线
            painter.drawLine(x, bot, x, y_l)
        if c < o: 
            # 填充实体（空阳线）
            painter.fillRect(body_x, top, body_w, body_h, QBrush(kcolor))

        painter.restore()
