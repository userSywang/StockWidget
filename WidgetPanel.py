import json
import requests, keyboard
from urllib.parse import quote
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import time

from PySide6.QtCore import Qt, QEvent, QTimer, Signal
from PySide6.QtGui import QFont, QAction, QColor
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableView, QHeaderView, QAbstractItemView, QFrame, QStyledItemDelegate

from Display import SimpleTableModel, KLineDelegate
from Display import PriceAlertNameDelegate
from KLineChart import KLineChartDialog
from StockLogic import (
    DEFAULT_WARNING_TEXT,
    evaluate_alert_rules,
    evaluate_price_alerts,
    evaluate_strategy_alerts,
    flatten_group_codes,
    moving_average,
    normalize_alert_rules,
    normalize_code_or_none,
    normalize_groups,
    normalize_codes,
    normalize_price_alerts,
    price_alert_is_expired,
    normalize_strategy_alert_config,
    strategy_daily_request_codes,
    strategy_request_codes,
    update_strategy_position_state,
)

STRATEGY_DAILY_SUMMARY_SLOTS = ((9, 0, "09:00"), (18, 0, "18:00"))
STRATEGY_DAILY_SUMMARY_GRACE_MINUTES = 10

class FloatLabel(QWidget):
    hotkey_triggered = Signal()
    def __init__(self, cfg: dict):
        super().__init__()
        self._on_change = (lambda: None)
        self._open_settings_cb = None
        self._fit_pending = False
        self._last_fit_signature = None
        self._suspend_keep_top_until = 0.0

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

        # 加载配置
        codes_cfg               = cfg.get("codes",["sh000001"])             # 自选列表
        groups_cfg              = cfg.get("groups", [])                     # 分组自选列表
        checked_codes_cfg       = cfg.get("checked_codes", cfg.get("visible_codes", codes_cfg))  # 在浮窗中显示的股票（新名 checked_codes，兼容 visible_codes）
        self.refresh_seconds    = int(cfg.get("refresh_seconds", 2))        # 刷新间隔
        flags_cfg               = cfg.get("flags", {})                      # 指标开关（字典格式）
        self.short_code         = bool(cfg.get("short_code", False))
        self.name_length        = int(cfg.get("name_length",0))
        # b1s1_display: 'qty'|'price'|'both'。兼容旧配置键 b1s1_price (bool)
        b1s1_display_cfg = cfg.get("b1s1_display", None)
        if isinstance(b1s1_display_cfg, str) and b1s1_display_cfg in ("qty", "price", "both"):
            self.b1s1_display = b1s1_display_cfg
        else:
            # 旧配置兼容：若 b1s1_price 为 True 则默认显示价格，否则显示数量
            self.b1s1_display = "price" if bool(cfg.get("b1s1_price", False)) else "qty"
        
        # 防止买一/卖一同步时触发重复处理
        self._syncing_b1s1 = False

        self.header_visible     = bool(cfg.get("header_visible", False))    # 表头可见
        self.grid_visible       = bool(cfg.get("grid_visible", False))      # 网格可见

        font_family             = cfg.get("font_family", "Microsoft YaHei") # 字体类型
        font_size               = int(cfg.get("font_size", 10))             # 字体大小
        self.line_extra_px      = int(cfg.get("line_extra_px", 1))          # 行间距
        self.fg                 = QColor(cfg.get("fg", "#FFFFFF"))        # 前景色
        bg                      = cfg.get("bg", {"r":0,"g":0,"b":0,"a":191})# 背景色
        self.opacity_pct        = int(cfg.get("opacity_pct", 90))           # 透明度
        self.default_color      = bool(cfg.get("default_color", False))     # 默认颜色模式

        self.hotkey             = cfg.get("hotkey", "Ctrl+Alt+F")           # 快捷键
        self.start_on_boot      = bool(cfg.get("start_on_boot", False))
        self.alert_rules        = normalize_alert_rules(cfg.get("alert_rules", []))
        self.price_alerts       = normalize_price_alerts(cfg.get("price_alerts", []))
        self.strategy_alert_config = normalize_strategy_alert_config(cfg.get("strategy_alert_config", {}))
        self.panel_display_mode = "quotes"
        self.warning_visible    = bool(cfg.get("warning_visible", False))
        self.warning_text       = str(cfg.get("warning_text", DEFAULT_WARNING_TEXT)).strip() or DEFAULT_WARNING_TEXT
        self.market_amount_visible = bool(cfg.get("market_amount_visible", False))
        self.price_alert_badge_visible = bool(cfg.get("price_alert_badge_visible", True))
        self.code_names         = dict(cfg.get("code_names", {})) if isinstance(cfg.get("code_names"), dict) else {}
        self.code_tags          = self._normalize_code_tags(cfg.get("code_tags", {}))
        self.data_source        = self._normalize_data_source(cfg.get("data_source", {}))
        self._latest_quotes     = {}
        self._http              = requests.Session()
        self._refresh_executor  = ThreadPoolExecutor(max_workers=1)
        self._refresh_future    = None
        self._refresh_previous_quotes = {}
        self._refresh_again_requested = False
        self._refresh_again_force = False
        self._strategy_push_sent_keys = set()
        self._strategy_push_sent_at = {}
        self._desktop_alert_ignored_today = self._normalize_desktop_alert_ignored_today(
            cfg.get("desktop_alert_ignored_today", {})
        )
        self.strategy_alert_history = self._normalize_strategy_alert_history(cfg.get("strategy_alert_history", []))
        self._strategy_daily_summary_sent_date = str(cfg.get("strategy_daily_summary_sent_date") or "")
        self._latest_strategy_states = []
        self._daily_kline_cache = {}
        self._intraday_trend_cache = {}
        self._intraday_sample_cache = {}
        self._latest_daily_by_code = {}
        self._kline_chart_dialog = None
        self._kline_chart_code = ""

        # 设置初值
        self.groups = normalize_groups(groups_cfg, codes_cfg)
        self.codes = flatten_group_codes(self.groups)
        # 列标题列表（提前定义，供后续旧配置解析使用）
        self.ALL_HEADERS = ["代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价", "K线", "MA5", "MA10", "MA20", "持仓盈亏", "止损线", "策略状态"]

        # 列显示标志（独立属性）
        # 解析旧 flags 配置以做回退
        old_flags = {}
        if isinstance(flags_cfg, list):
            for i, h in enumerate(self.ALL_HEADERS):
                old_flags[h] = bool(flags_cfg[i]) if i < len(flags_cfg) else False
        elif isinstance(flags_cfg, dict):
            for h in self.ALL_HEADERS:
                old_flags[h] = bool(flags_cfg.get(h, False))

        # 新：为每一列创建独立的 bool 属性（优先读取新配置，否则回退到 old_flags）
        self.code_visible = bool(cfg.get("code_visible", old_flags.get("代码", False)))
        self.name_visible = bool(cfg.get("name_visible", old_flags.get("名称", False)))
        self.price_visible = bool(cfg.get("price_visible", old_flags.get("现价", False)))
        self.change_visible = bool(cfg.get("change_visible", old_flags.get("涨跌值", False)))
        self.change_pct_visible = bool(cfg.get("change_pct_visible", old_flags.get("涨跌幅", False)))
        # 买一/卖一 使用单一开关 b1s1_visible（用户要求不要拆分控制）
        self.b1s1_visible = bool(cfg.get("b1s1_visible", (old_flags.get("买一", False) or old_flags.get("卖一", False))))
        self.commi_visible = bool(cfg.get("commi_visible", old_flags.get("委比", False)))
        self.vol_visible = bool(cfg.get("vol_visible", old_flags.get("成交量", False)))
        self.amount_visible = bool(cfg.get("amount_visible", old_flags.get("成交额", False)))
        self.avg_visible = bool(cfg.get("avg_visible", old_flags.get("均价", False)))
        self.kline_visible = bool(cfg.get("kline_visible", old_flags.get("K线", False)))
        self.ma5_visible = bool(cfg.get("ma5_visible", old_flags.get("MA5", False)))
        self.ma10_visible = bool(cfg.get("ma10_visible", old_flags.get("MA10", False)))
        self.ma20_visible = bool(cfg.get("ma20_visible", old_flags.get("MA20", False)))
        self.strategy_profit_visible = bool(cfg.get("strategy_profit_visible", old_flags.get("持仓盈亏", False)))
        self.strategy_stop_visible = bool(cfg.get("strategy_stop_visible", old_flags.get("止损线", False)))
        self.strategy_status_visible = bool(cfg.get("strategy_status_visible", old_flags.get("策略状态", False)))

        # 设置自选显示股票（新名 checked_codes）
        checked_codes_cfg = checked_codes_cfg or self.codes
        checked_norm = normalize_codes(checked_codes_cfg)
        self.checked_codes = [c for c in checked_norm if c in self.codes]
        if not self.checked_codes:
            self.checked_codes = list(self.codes)
        self.font = QFont(font_family, max(8, min(15, font_size)))
        self.bg = QColor(bg["r"],bg["g"],bg["b"],bg["a"])
        
        
        self.hotkey_triggered.connect(self.toggle_win)
        self._register_hotkey()

        # UI
        self.panel = QWidget(self)
        self.panel.setObjectName("panel")
        self.vbox = QVBoxLayout(self.panel)
        self.vbox.setContentsMargins(10,6,10,6)
        self.vbox.setSpacing(0)

        self.table = QTableView(self.panel)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.setWordWrap(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(self.header_visible)
        self.table.horizontalHeader().setStretchLastSection(False)
        # Column widths are calculated from stock rows in _fit_to_contents().
        # ResizeToContents would later measure spanned message rows and expand
        # the first column again after warning/alert text is rendered.
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.setFont(self.font)
        self.table.horizontalHeader().setFont(self.font)
        self.table.verticalHeader().setMinimumSectionSize(1)
        self.table.verticalHeader().setDefaultSectionSize(1)
        self.table.horizontalHeader().setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.error_label = QLabel("", self.panel)
        self.error_label.setStyleSheet("color: #ff6666; padding: 2px 4px;")
        self.error_label.setVisible(False)
        self.vbox.addWidget(self.error_label)

        self.model = SimpleTableModel(headers=self.ALL_HEADERS, align_right_cols=[1,2,3,4,5])
        self.model.set_color_scheme(self.default_color, self.fg)
        self.table.setModel(self.model)

        self.k_delegate = KLineDelegate(self.table, base_pt=12)
        self.k_delegate.update_scheme(self.default_color, self.fg)
        self.k_delegate.set_point_size(self.font.pointSize())
        self.k_column_visible_index = None
        self.name_delegate = PriceAlertNameDelegate(self.table)
        self.name_delegate.update_scheme(self.fg)
        self.name_column_visible_index = None

        self.vbox.addWidget(self.table)

        for w in (self.panel, self.table, self.table.viewport(), self.table.horizontalHeader(), self.table.verticalHeader()):
            w.installEventFilter(self)

        self.apply_style()
        self.set_window_opacity_percent(self.opacity_pct)
        self._fit_to_contents()

        scr = QApplication.primaryScreen().availableGeometry()
        pos = cfg.get("pos")
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            x, y = int(pos["x"]), int(pos["y"])
            x = max(scr.left(), min(x, scr.right()-self.width()))
            y = max(scr.top(),  min(y, scr.bottom()-self.height()))
            self.move(x, y)
        else:
            self.move(scr.right()-self.width()-40, scr.bottom()-self.height()-80)

        self._drag_pos = None
        self._drag_moved = False
        self._drag_press_global = None
        self._pressed_kline_code = ""

        self.timer = QTimer(self)
        self.timer.setInterval(max(1, self.refresh_seconds)*1000)
        self.timer.timeout.connect(self._refresh_from_function)
        self.timer.start()
        self._refresh_from_function(force=True)
        self._defer_fit()

        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.setInterval(1000)  # 每 1000ms 检查一次
        self._keep_top_timer.timeout.connect(self._ensure_on_top)
        self._keep_top_timer.start()

    # 与 App 连接
    def set_open_settings_callback(self, fn): 
        self._open_settings_cb = fn

    def set_on_change(self, fn): 
        self._on_change = fn or (lambda: None)

    def _notify_change(self):
        cb = getattr(self, "_on_change", None)
        if callable(cb): cb()

    def current_config(self):
        return {
            "groups": self.groups,
            "codes": self.codes,
            "checked_codes": self.checked_codes,
            "alert_rules": self.alert_rules,
            "price_alerts": self.price_alerts,
            "strategy_alert_config": self.strategy_alert_config,
            "strategy_alert_history": self.strategy_alert_history,
            "strategy_daily_summary_sent_date": getattr(self, "_strategy_daily_summary_sent_date", ""),
            "desktop_alert_ignored_today": self._normalize_desktop_alert_ignored_today(
                getattr(self, "_desktop_alert_ignored_today", {})
            ),
            "warning_visible": self.warning_visible,
            "warning_text": self.warning_text,
            "market_amount_visible": bool(self.market_amount_visible),
            "price_alert_badge_visible": bool(getattr(self, "price_alert_badge_visible", True)),
            "code_names": self.code_names,
            "code_tags": self.code_tags,
            "code_visible": bool(getattr(self, 'code_visible', False)),
            "name_visible": bool(getattr(self, 'name_visible', False)),
            "price_visible": bool(getattr(self, 'price_visible', False)),
            "change_visible": bool(getattr(self, 'change_visible', False)),
            "change_pct_visible": bool(getattr(self, 'change_pct_visible', False)),
            "b1s1_visible": bool(getattr(self, 'b1s1_visible', False)),
            "commi_visible": bool(getattr(self, 'commi_visible', False)),
            "vol_visible": bool(getattr(self, 'vol_visible', False)),
            "amount_visible": bool(getattr(self, 'amount_visible', False)),
            "avg_visible": bool(getattr(self, 'avg_visible', False)),
            "kline_visible": bool(getattr(self, 'kline_visible', False)),
            "ma5_visible": bool(getattr(self, 'ma5_visible', False)),
            "ma10_visible": bool(getattr(self, 'ma10_visible', False)),
            "ma20_visible": bool(getattr(self, 'ma20_visible', False)),
            "strategy_profit_visible": bool(getattr(self, 'strategy_profit_visible', False)),
            "strategy_stop_visible": bool(getattr(self, 'strategy_stop_visible', False)),
            "strategy_status_visible": bool(getattr(self, 'strategy_status_visible', False)),
            "short_code": self.short_code,
            "name_length": self.name_length,
            "b1s1_price": (getattr(self, 'b1s1_display', 'qty') == 'price'),
            "b1s1_display": getattr(self, 'b1s1_display', 'qty'),
            "header_visible": self.header_visible,
            "grid_visible": self.grid_visible,
            "refresh_seconds": self.refresh_seconds,
            "fg": self.fg.name(QColor.HexRgb),
            "bg": {"r": self.bg.red(), "g": self.bg.green(), "b": self.bg.blue(), "a": self.bg.alpha()},
            "opacity_pct": int(round(self.windowOpacity()*100)),
            "font_family": self.font.family(),
            "font_size": self.font.pointSize(),
            "line_extra_px": self.line_extra_px,
            "default_color": self.default_color,
            "pos": {"x": self.x(), "y": self.y()},
            "hotkey": self.hotkey,
            "start_on_boot": bool(self.start_on_boot),
            "data_source": self.data_source,
        }

    @staticmethod
    def _normalize_code_tags(code_tags):
        if not isinstance(code_tags, dict):
            return {}
        allowed_holding = {"", "hold", "watch", "cleared"}
        allowed_cycle = {"", "short", "swing", "long"}
        allowed_priority = {"", "focus", "normal", "low"}
        normalized = {}
        for raw_code, raw_tags in code_tags.items():
            code = normalize_code_or_none(raw_code)
            if not code or not isinstance(raw_tags, dict):
                continue
            holding = str(raw_tags.get("holding") or "").strip()
            cycle = str(raw_tags.get("cycle") or "").strip()
            priority = str(raw_tags.get("priority") or "").strip()
            item = {
                "holding": holding if holding in allowed_holding else "",
                "cycle": cycle if cycle in allowed_cycle else "",
                "priority": priority if priority in allowed_priority else "",
            }
            if any(item.values()):
                normalized[code] = item
        return normalized

    def set_code_tags(self, code_tags):
        self.code_tags = self._normalize_code_tags(code_tags)
        valid_codes = set(getattr(self, "codes", []))
        self.code_tags = {code: tags for code, tags in self.code_tags.items() if code in valid_codes}
        self._notify_change()

    @staticmethod
    def _normalize_data_source(data_source):
        if not isinstance(data_source, dict):
            data_source = {}
        mode = data_source.get("mode")
        if mode not in ("sina", "custom"):
            mode = "sina"
        headers = data_source.get("headers")
        if not isinstance(headers, dict):
            headers = {}
        fields = data_source.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        return {
            "mode": mode,
            "url_template": str(data_source.get("url_template") or "").strip(),
            "headers": {str(k): str(v) for k, v in headers.items() if str(k).strip()},
            "fields": dict(fields),
        }

    @staticmethod
    def _normalize_strategy_alert_history(history):
        normalized = []
        for item in history or []:
            if not isinstance(item, dict):
                continue
            code = normalize_code_or_none(item.get("code"))
            if not code:
                continue
            normalized.append({
                "time": str(item.get("time") or "").strip(),
                "code": code,
                "name": str(item.get("name") or code).strip(),
                "status": str(item.get("status") or "").strip(),
                "severity": str(item.get("severity") or "neutral").strip(),
            })
        return normalized[:50]

    @staticmethod
    def _normalize_desktop_alert_ignored_today(value):
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for raw_key, raw_day in value.items():
            key = str(raw_key or "").strip()
            day = str(raw_day or "").strip()[:10]
            if key and day:
                normalized[key] = day
        return normalized

    def header_is_visible(self, header: str) -> bool:
        """返回指定列标题对应的独立可见属性值（替代旧的 flags 字典）。"""
        try:
            if header == "代码":
                return bool(getattr(self, 'code_visible', False))
            if header == "名称":
                return bool(getattr(self, 'name_visible', False))
            if header == "现价":
                return bool(getattr(self, 'price_visible', False))
            if header == "涨跌值":
                return bool(getattr(self, 'change_visible', False))
            if header == "涨跌幅":
                return bool(getattr(self, 'change_pct_visible', False))
            if header in ("买一", "卖一"):
                return bool(getattr(self, 'b1s1_visible', False))
            if header == "委比":
                return bool(getattr(self, 'commi_visible', False))
            if header == "成交量":
                return bool(getattr(self, 'vol_visible', False))
            if header == "成交额":
                return bool(getattr(self, 'amount_visible', False))
            if header == "均价":
                return bool(getattr(self, 'avg_visible', False))
            if header == "K线":
                return bool(getattr(self, 'kline_visible', False))
            if header == "MA5":
                return bool(getattr(self, 'ma5_visible', False))
            if header == "MA10":
                return bool(getattr(self, 'ma10_visible', False))
            if header == "MA20":
                return bool(getattr(self, 'ma20_visible', False))
            if header == "持仓盈亏":
                return bool(getattr(self, 'strategy_profit_visible', False))
            if header == "止损线":
                return bool(getattr(self, 'strategy_stop_visible', False))
            if header == "策略状态":
                return bool(getattr(self, 'strategy_status_visible', False))
        except Exception:
            pass
        return False

    # ----- 外观/尺寸 -----
    def apply_style(self):
        r,g,b,a = self.bg.red(), self.bg.green(), self.bg.blue(), self.bg.alpha()
        fg_r, fg_g, fg_b = self.fg.red(), self.fg.green(), self.fg.blue()
        line_col = f"rgba({fg_r},{fg_g},{fg_b},80)"
        self.panel.setStyleSheet(f"""
            QWidget#panel {{
                background: rgba({r},{g},{b},{a});
                border-radius: 5px;
            }}
            QTableView {{
                background: transparent;
                border: {f"1px solid {line_col}" if self.grid_visible else "none"};
                border-radius: 3px;
                {"" if self.default_color else f"color: {self.fg.name()};"}
                outline: none;
            }}
            QTableView::item {{
                border-right: {f"1px solid {line_col}" if self.grid_visible else "none"};
                border-bottom: {f"1px solid {line_col}" if self.grid_visible else "none"};
            }}
            QHeaderView {{
                background-color: transparent;
            }}
            QHeaderView::section {{
                background: transparent;
                border: none;
                border-bottom: 1px solid {line_col};
                font-weight: 600;
                {"" if self.default_color else f"color: {self.fg.name()};"}
                padding: 2px 4px;
            }}
        """)
        self.table.setFont(self.font)
        self.table.horizontalHeader().setFont(self.font)
        self._defer_fit()

    def _apply_row_heights(self):
        fm = self.table.fontMetrics()
        h = fm.height() + max(0, self.line_extra_px)
        span_width = max(40, sum(self.table.columnWidth(c) for c in range(self.model.columnCount())) - 8)
        self.table.verticalHeader().setDefaultSectionSize(h)
        for r in range(self.model.rowCount()):
            meta = self.model._row_meta[r] if 0 <= r < len(getattr(self.model, "_row_meta", [])) else {}
            if meta.get("row_type") == "separator":
                self.table.setRowHeight(r, max(4, h // 2))
            elif meta.get("row_type") in ("alert", "warning"):
                row = self.model._rows[r] if 0 <= r < len(getattr(self.model, "_rows", [])) else [meta.get("text", "")]
                text = str(row[0] if row else meta.get("text", "") or "")
                rect = fm.boundingRect(0, 0, span_width, 10000, Qt.TextWordWrap | Qt.AlignVCenter, text)
                self.table.setRowHeight(r, max(h, rect.height() + 6))
            else:
                self.table.setRowHeight(r, h)

    @staticmethod
    def _column_width_source_rows(rows, meta):
        result = []
        for i, row in enumerate(rows or []):
            row_meta = meta[i] if i < len(meta or []) else {}
            if not (row_meta or {}).get("row_type"):
                result.append(row)
        return result

    @staticmethod
    def _wrap_text_for_width(text, max_width, measure):
        text = str(text or "")
        try:
            max_width = int(max_width)
        except Exception:
            max_width = 0
        if max_width <= 0 or not text:
            return text
        lines = []
        paragraphs = text.splitlines() or [""]
        for paragraph in paragraphs:
            current = ""
            for ch in paragraph:
                trial = current + ch
                if current and measure(trial) > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current = trial
            lines.append(current)
        return "\n".join(lines)

    def _resize_columns_to_contents(self):
        headers = list(getattr(self.model, "_headers", []) or [])
        rows = list(getattr(self.model, "_rows", []) or [])
        meta = list(getattr(self.model, "_row_meta", []) or [])
        col_count = self.model.columnCount()
        body_fm = self.table.fontMetrics()
        header_fm = self.table.horizontalHeader().fontMetrics()
        for c in range(col_count):
            header = headers[c] if c < len(headers) else ""
            width = header_fm.horizontalAdvance(str(header)) + 14 if self.header_visible else 0
            for row_index, row in enumerate(rows):
                row_meta = meta[row_index] if row_index < len(meta) else {}
                if (row_meta or {}).get("row_type"):
                    continue
                cell = row[c] if c < len(row) else ""
                if isinstance(cell, dict) and "k" in cell:
                    cell_width = max(46, body_fm.height() * 3)
                else:
                    cell_width = body_fm.horizontalAdvance(str(cell)) + 12
                    if header == "名称":
                        if row_meta.get("price_alerts"):
                            cell_width += 22
                width = max(width, cell_width)
            self.table.setColumnWidth(c, max(18, width))

    def _wrap_message_rows_to_current_width(self):
        rows = getattr(self.model, "_rows", [])
        meta = getattr(self.model, "_row_meta", [])
        if not rows or not meta:
            return
        span_width = max(40, sum(self.table.columnWidth(c) for c in range(self.model.columnCount())) - 8)
        fm = self.table.fontMetrics()
        for r, row_meta in enumerate(meta):
            if not (row_meta or {}).get("row_type") in ("alert", "warning"):
                continue
            if r >= len(rows) or not rows[r]:
                continue
            rows[r][0] = self._wrap_text_for_width(
                row_meta.get("text", ""),
                span_width,
                fm.horizontalAdvance,
            )

    def _fit_to_contents(self):
        fit_sig = self._fit_signature()
        if fit_sig == getattr(self, "_last_fit_signature", None):
            return
        self._last_fit_signature = fit_sig

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Fixed)
        self._resize_columns_to_contents()
        self._wrap_message_rows_to_current_width()
        self._apply_row_heights()

        cols = self.model.columnCount()
        rows = self.model.rowCount()
        total_w = self.table.verticalHeader().width() + 2*self.table.frameWidth()
        for c in range(cols): 
            total_w += self.table.columnWidth(c)
        hh = self.table.horizontalHeader().height() if self.table.horizontalHeader().isVisible() else 0
        total_h = hh + 2*self.table.frameWidth()
        for r in range(rows): 
            total_h += self.table.rowHeight(r)
        # Qt occasionally needs a few spare pixels after header/row rounding;
        # without this, scrollbars can appear even when content nominally fits.
        total_w += 14
        total_h += 8
        self.table.setFixedSize(max(1, total_w), max(1, total_h))
        self.panel.adjustSize()
        self.resize(self.panel.size())
        self._keep_window_inside_screen()

    def _keep_window_inside_screen(self):
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            rect = screen.availableGeometry()
            max_x = max(rect.left(), rect.right() - self.width())
            max_y = max(rect.top(), rect.bottom() - self.height())
            x = max(rect.left(), min(self.x(), max_x))
            y = max(rect.top(), min(self.y(), max_y))
            if x != self.x() or y != self.y():
                self.move(x, y)
                self._notify_change()
        except Exception:
            pass

    def _defer_fit(self):
        if getattr(self, "_fit_pending", False):
            return
        self._fit_pending = True
        QTimer.singleShot(0, self._run_deferred_fit)

    def _run_deferred_fit(self):
        self._fit_pending = False
        self._fit_to_contents()

    def _fit_signature(self):
        rows = getattr(self.model, "_rows", [])
        headers = getattr(self.model, "_headers", [])
        meta = getattr(self.model, "_row_meta", [])
        row_types = tuple((m or {}).get("row_type", "") for m in meta)
        price_alert_meta = tuple(
            (
                bool((m or {}).get("price_alerts")),
                any(bool(a.get("triggered")) for a in ((m or {}).get("price_alerts") or []) if isinstance(a, dict)),
            )
            for m in meta
        )
        text_lengths = tuple(tuple(len(str(cell)) for cell in row) for row in rows)
        return (
            tuple(headers),
            text_lengths,
            row_types,
            price_alert_meta,
            bool(self.header_visible),
            bool(self.grid_visible),
            self.font.family(),
            self.font.pointSize(),
            int(self.line_extra_px),
        )

    # ----- 数据 & 投影 -----
    def _show_error(self, msg: str):
        try:
            if self.k_column_visible_index is not None:
                self.table.setItemDelegateForColumn(self.k_column_visible_index, QStyledItemDelegate(self.table))
                self.k_column_visible_index = None
        except Exception:
            pass
        try:
            text = str(msg) if msg is not None else ""
            # 若是 requests 抛出的网络错误，显示更友好的中文提示
            if isinstance(msg, Exception):
                import requests as _req
                if isinstance(msg, _req.exceptions.RequestException):
                    text = "无网络连接"
        except Exception:
            text = str(msg)

        if hasattr(self, 'error_label'):
            self.error_label.setText(text)
            self.error_label.setVisible(True)
        self._defer_fit()

    def _clear_error(self):
        # 清除顶部错误提示
        if hasattr(self, 'error_label'):
            try:
                self.error_label.setVisible(False)
                self.error_label.setText("")
            except Exception:
                pass

    # ----- 数据来源：新浪财经 -----
    def _format_plain_quote(self, code, quote):
        def num(name, default=0.0):
            try:
                return float(quote.get(name, default) or default)
            except Exception:
                return float(default)

        name = str(quote.get("name") or code)
        current_price = num("price")
        change = num("change")
        change_pct = num("change_pct")
        prev_close = num("prev_close")
        if prev_close <= 0 and current_price and change:
            prev_close = current_price - change
        if prev_close <= 0 and current_price and change_pct:
            prev_close = current_price / (1 + change_pct / 100.0)
        if not change and prev_close:
            change = current_price - prev_close
        if not change_pct and prev_close:
            change_pct = (current_price / prev_close - 1) * 100

        opening_price = num("open", current_price)
        high_price = num("high", max(opening_price, current_price))
        low_price = num("low", min(opening_price, current_price))
        volume = num("volume")
        amount = num("amount")
        avg = num("avg", current_price if current_price else prev_close)
        etf = len(code) > 2 and code[2] in ("1", "5")
        decimals = 3 if etf else 2
        arrow = " "
        if high_price > low_price:
            if round(current_price, decimals) == round(high_price, decimals):
                arrow = "↑"
            elif round(current_price, decimals) == round(low_price, decimals):
                arrow = "↓"

        display_code = code[2:] if self.short_code and len(code) > 2 else code
        display_name = name if self.name_length == 0 else name[:self.name_length]
        row = [
            display_code,
            display_name,
            f"{current_price:.{decimals}f}{arrow}" if current_price else "-",
            f"{change:+.{decimals}f}" if current_price else "-",
            f"{change_pct:+.2f}%" if current_price else "无数据",
            "-",
            "-",
            "-",
            f"{volume}" if volume < 1e4 else (f"{volume/1e4:.2f}万" if volume < 1e8 else f"{volume/1e8:.2f}亿"),
            f"{amount/1e4:.2f}万" if amount < 1e8 else (f"{amount/1e8:.2f}亿" if amount < 1e12 else f"{amount/1e12:.2f}万亿"),
            f"{avg:.{decimals}f}" if avg else "-",
            {"k": (opening_price, current_price, high_price, low_price, prev_close)},
        ]
        sign = {
            "delta": (change > 0) - (change < 0),
            "commi": 0,
            "avg": (avg > prev_close) - (avg < prev_close) if prev_close else 0,
            "b1": 0,
            "s1": 0,
        }
        stored = {
            "name": name,
            "price": current_price,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "amount": amount,
            "open": opening_price,
            "high": high_price,
            "low": low_price,
            "prev_close": prev_close,
            "avg": avg,
        }
        return row, sign, stored

    def _custom_value(self, item, logical_name, fallback_names):
        fields = getattr(self, "data_source", {}).get("fields", {})
        names = [fields.get(logical_name)] if fields.get(logical_name) else []
        names.extend(fallback_names)
        for name in names:
            if name in item:
                return item.get(name)
        return None

    def _extract_custom_items(self, payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "quotes", "items", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            return [dict(value, code=key) for key, value in payload.items() if isinstance(value, dict)]
        return []

    def _get_custom_price(self, requested_codes):
        source = getattr(self, "data_source", {})
        template = str(source.get("url_template") or "").strip()
        if not template:
            raise Exception("自定义数据源未配置接口地址")
        label = ",".join(requested_codes)
        url = template.replace("{codes}", label).replace("{codes_url}", quote(label, safe=""))
        headers = dict(source.get("headers") or {})
        getter = getattr(getattr(self, "_http", None), "get", requests.get)
        response = getter(url, headers=headers, timeout=5)
        try:
            payload = response.json()
        except Exception:
            payload = json.loads(getattr(response, "text", "") or "null")

        row_by_code = {}
        sign_by_code = {}
        quote_by_code = {}
        for item in self._extract_custom_items(payload):
            if not isinstance(item, dict):
                continue
            raw_code = self._custom_value(item, "code", ["code", "symbol", "ts_code"])
            codes = normalize_codes([raw_code])
            if not codes:
                continue
            code = codes[0]
            quote_data = {
                "name": self._custom_value(item, "name", ["name", "short_name", "title"]),
                "price": self._custom_value(item, "price", ["price", "current", "last", "close"]),
                "change": self._custom_value(item, "change", ["change", "chg"]),
                "change_pct": self._custom_value(item, "change_pct", ["change_pct", "pct", "percent"]),
                "volume": self._custom_value(item, "volume", ["volume", "vol"]),
                "amount": self._custom_value(item, "amount", ["amount", "turnover"]),
                "open": self._custom_value(item, "open", ["open", "opening_price"]),
                "high": self._custom_value(item, "high", ["high", "high_price"]),
                "low": self._custom_value(item, "low", ["low", "low_price"]),
                "prev_close": self._custom_value(item, "prev_close", ["prev_close", "pre_close", "yesterday_close"]),
                "avg": self._custom_value(item, "avg", ["avg", "average"]),
            }
            row, sign, stored = self._format_plain_quote(code, quote_data)
            row_by_code[code] = row
            sign_by_code[code] = sign
            quote_by_code[code] = stored

        for code in requested_codes:
            if code not in row_by_code:
                row, sign, _ = self._format_plain_quote(code, {"name": code, "price": 0})
                row_by_code[code] = row
                sign_by_code[code] = sign
        return row_by_code, sign_by_code, quote_by_code

    def lookup_code_names(self, codes):
        requested_codes = normalize_codes(codes)
        missing = [code for code in requested_codes if not str(self.code_names.get(code) or "").strip()]
        if not missing:
            return {code: self.code_names.get(code, "") for code in requested_codes}
        _, _, quote_by_code = self._get_price(missing)
        for code, quote in quote_by_code.items():
            name = str((quote or {}).get("name") or "").strip()
            if name:
                self.code_names[code] = name
        self._notify_change()
        return {code: self.code_names.get(code, "") for code in requested_codes}

    def _get_price(self, codes:list):
        requested_codes = normalize_codes(codes)
        if getattr(self, "data_source", {}).get("mode") == "custom":
            return self._get_custom_price(requested_codes)
        label = ",".join(requested_codes)
        if not label:
            raise Exception("暂无数据，请添加自选")

        row_by_code = {}
        sign_by_code = {}
        quote_by_code = {}
        url = 'https://hq.sinajs.cn/list=' + label
        headers = {'Referer': 'https://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0'}
        getter = getattr(getattr(self, "_http", None), "get", requests.get)
        r = getter(url, headers=headers, timeout=3)
        r.encoding = 'gbk'
        for line in r.text.split('\n'):
            if not line or '"' not in line:
                continue
            heads = line.split('="')[0].split('_')
            parts = line.split('="')[1].split(',')
            if len(parts) < 30:
                continue

            code          = heads[2]
            name          = parts[0]
            opening_price = float(parts[1] or 0)   # 开盘
            prev_close    = float(parts[2] or 0)   # 昨收
            current_price = float(parts[3] or 0)   # 现价
            high_price    = float(parts[4] or 0)   # 当日最高
            low_price     = float(parts[5] or 0)   # 当日最低
            first_pur     = float(parts[6] or 0)   # 买一
            first_sell    = float(parts[7] or 0)   # 卖一
            deals_vol     = float(parts[8] or 0)   # 成交量
            deals_amt     = float(parts[9] or 0)   # 成交额
            purchaser     = [int(x or 0) for x in parts[10:19:2]]  # 买盘，股数
            pur_price     = [float(x or 0) for x in parts[11:20:2]]  # 买盘，价格
            seller        = [int(x or 0) for x in parts[20:29:2]]  # 卖盘，股数
            sel_price     = [float(x or 0) for x in parts[21:30:2]]  # 卖盘，价格
            update_date   = [int(x or 0) for x in parts[30].split('-')]  # 日期
            update_time   = [int(x or 0) for x in parts[31].split(':')]  # 时间

            etf = code[2] in ('1','5')

            # 构建买一/卖一数据及其颜色信息，并添加位置箭头
            b1_label = ""
            s1_label = ""
            b1_color_sign = 0  # 买一颜色：1红 0中性 -1绿
            s1_color_sign = 0  # 卖一颜色：1红 0中性 -1绿

            # 决定小数精度用于比较是否相等（避免浮点微小误差）
            dec = 3 if etf else 2
            def almost_eq(a, b):
                try:
                    return round(float(a), dec) == round(float(b), dec)
                except Exception:
                    return False

            # 标记：买一箭头位于右侧 '<'，卖一箭头位于左侧 '>'
            buy_marker = " "
            sell_marker = " "
            if first_pur > 0 and almost_eq(current_price, first_pur):
                buy_marker = "<"
            if first_sell > 0 and almost_eq(current_price, first_sell):
                sell_marker = ">"

            if first_pur == first_sell > 0:
                # 集合竞价：配对量 / 未配对量
                # 此处不显示成交方向箭头（竞价阶段无 <> 指示），且配对量和未配对量使用统一颜色规则
                current_price = first_sell  # 9:15 ~ 9:25; 14:57 ~ 15:00 竞价
                paired = seller[0]
                # unpaired_sign: >0 表示买方优势，<0 表示卖方优势
                unpaired_sign = -seller[1] if seller[1] > 0 else purchaser[1]
                # 显示数量（手）或价格或数量和价格（手数(价格)）
                paired_cnt = int(paired/100)
                unpaired_cnt = int(unpaired_sign/100)
                b_price = f"{first_pur:.3f}" if etf else f"{first_pur:.2f}"
                s_price = f"{first_sell:.3f}" if etf else f"{first_sell:.2f}"
                mode = getattr(self, 'b1s1_display', 'qty')
                if mode == 'price':
                    b1_label = f"{b_price}"
                    s1_label = f"{s_price}"
                elif mode == 'both':
                    b1_label = f"{paired_cnt:d}({b_price})"
                    s1_label = f"{unpaired_cnt:+d}({s_price})"
                else:
                    b1_label = f"{paired_cnt:d}"
                    s1_label = f"{unpaired_cnt:+d}"
                # 竞价颜色：根据未配对量的方向
                if unpaired_sign > 0:
                    b1_color_sign = 1
                    s1_color_sign = 1
                elif unpaired_sign < 0:
                    b1_color_sign = -1
                    s1_color_sign = -1
                else:
                    b1_color_sign = 0
                    s1_color_sign = 0
            else:
                # 连续竞价：买一数量/卖一数量
                if first_pur > 0:
                    cnt = f"{int(purchaser[0]/100)}"
                    b_price = f"{first_pur:.3f}" if etf else f"{first_pur:.2f}"
                    mode = getattr(self, 'b1s1_display', 'qty')
                    if mode == 'price':
                        b1_label = f"{b_price}{buy_marker}"
                    elif mode == 'both':
                        b1_label = f"{cnt}({b_price}){buy_marker}"
                    else:
                        b1_label = f"{cnt}{buy_marker}"
                else:
                    b1_label = f"-{buy_marker}"

                if first_sell > 0:
                    cnt = f"{int(seller[0]/100)}"
                    s_price = f"{first_sell:.3f}" if etf else f"{first_sell:.2f}"
                    mode = getattr(self, 'b1s1_display', 'qty')
                    if mode == 'price':
                        s1_label = f"{sell_marker}{s_price}"
                    elif mode == 'both':
                        s1_label = f"{sell_marker}{cnt}({s_price})"
                    else:
                        s1_label = f"{sell_marker}{cnt}"
                else:
                    s1_label = f"{sell_marker}-"

                # 连续竞价时：买一固定红色，卖一固定绿色
                b1_color_sign = 1
                s1_color_sign = -1
            
            if current_price == 0:
                current_price = prev_close # 9:00 ~ 9:15 无数据
            if opening_price == 0: 
                opening_price = current_price
                high_price = current_price
                low_price = current_price

            change = current_price - prev_close if prev_close else 0.0
            change_pct = (current_price / prev_close - 1) * 100 if prev_close else 0.0
            avg = (deals_amt / deals_vol) if deals_vol > 0 else prev_close # 均价
            p_sum, s_sum = sum(purchaser), sum(seller)
            committee = (100 * (p_sum - s_sum) / (p_sum + s_sum)) if (p_sum + s_sum) > 0 else 0.0 # 委比

            # 触及日高/低显示箭头
            arrow = " "
            if high_price > low_price:
                if current_price == high_price: arrow = "↑"
                elif current_price == low_price: arrow = "↓"

            k_payload = {"k": (opening_price, current_price, high_price, low_price, prev_close)}

            # "代码", "名称", "现价", "涨跌值", "涨跌幅", "买一", "卖一", "委比", "成交量", "成交额", "均价",  "K线"
            if code[2] not in ('1','5'):
                row = [
                    code[2:] if self.short_code else code,
                    name if self.name_length == 0 else name[:self.name_length],
                    f"{current_price:.2f}{arrow}",
                    f"{change:+.2f}",
                    f"{change_pct:+.2f}%",
                    b1_label,
                    s1_label,
                    f"{committee:+.2f}%",
                    f"{deals_vol}" if deals_vol<1e4 else (f"{deals_vol/1e4:.2f}万" if deals_vol<1e8 else f"{deals_vol/1e8:.2f}亿"),
                    f"{deals_amt/1e4:.2f}万" if deals_amt<1e8 else (f"{deals_amt/1e8:.2f}亿" if deals_amt<1e12 else f"{deals_amt/1e12:.2f}万亿"),
                    f"{avg:.2f}",
                    k_payload
                ]
            else:
                row = [
                    code[2:] if self.short_code else code,
                    name if self.name_length == 0 else name[:self.name_length],
                    f"{current_price:.3f}{arrow}",
                    f"{change:+.3f}",
                    f"{change_pct:+.2f}%",
                    b1_label,
                    s1_label,
                    f"{committee:+.2f}%",
                    f"{deals_vol}" if deals_vol<1e4 else (f"{deals_vol/1e4:.2f}万" if deals_vol<1e8 else f"{deals_vol/1e8:.2f}亿"),
                    f"{deals_amt/1e4:.2f}万" if deals_amt<1e8 else (f"{deals_amt/1e8:.2f}亿" if deals_amt<1e12 else f"{deals_amt/1e12:.2f}万亿"),
                    f"{avg:.3f}",
                    k_payload
                ]
            row_by_code[code] = row
            sign_by_code[code] = {
                "delta": (change > 0) - (change < 0), 
                "commi": (committee > 0) - (committee < 0),
                "avg": (avg > prev_close) - (avg < prev_close),
                "b1": b1_color_sign,
                "s1": s1_color_sign,
            }
            quote_by_code[code] = {
                "name": name,
                "price": current_price,
                "change": change,
                "change_pct": change_pct,
                "volume": deals_vol,
                "amount": deals_amt,
                "open": opening_price,
                "high": high_price,
                "low": low_price,
                "prev_close": prev_close,
                "avg": avg,
            }

        for code in requested_codes:
            if code in row_by_code:
                continue
            display_code = code[2:] if self.short_code and len(code) > 2 else code
            name = f"板块{code[2:]}" if code[:2] in ("bk", "gn", "sw") else code
            if self.name_length > 0:
                name = name[:self.name_length]
            row_by_code[code] = [
                display_code,
                name,
                "-",
                "-",
                "无数据",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "",
            ]
            sign_by_code[code] = {"delta": 0, "commi": 0, "avg": 0, "b1": 0, "s1": 0}

        return row_by_code, sign_by_code, quote_by_code

    def _message_row(self, text: str):
        row = [""] * len(self.ALL_HEADERS)
        row[0] = text
        return row

    def _separator_row(self):
        return self._message_row("")

    def _empty_stock_row(self, code: str):
        row = ["-"] * len(self.ALL_HEADERS)
        if "代码" in self.ALL_HEADERS:
            row[self.ALL_HEADERS.index("代码")] = code
        if "名称" in self.ALL_HEADERS:
            row[self.ALL_HEADERS.index("名称")] = self.code_names.get(code, code)
        return row

    def _market_amount_request_codes(self):
        return ["sh000001", "sz399001"] if getattr(self, "market_amount_visible", False) else []

    def _alert_request_codes(self):
        codes = []
        for rule in normalize_alert_rules(getattr(self, "alert_rules", [])):
            codes.extend([target.get("code") for target in rule.get("targets", [])])
        return normalize_codes(codes)

    def _strategy_request_codes(self):
        config = getattr(self, "strategy_alert_config", {})
        codes = strategy_request_codes(config)
        if normalize_strategy_alert_config(config).get("enabled"):
            codes.extend(strategy_daily_request_codes(config))
        return normalize_codes(codes)

    def _daily_request_codes(self):
        codes = []
        if any(getattr(self, attr, False) for attr in ("ma5_visible", "ma10_visible", "ma20_visible")):
            codes.extend(getattr(self, "checked_codes", []))
        if getattr(self, "_kline_chart_code", ""):
            codes.append(self._kline_chart_code)
        for alert in normalize_price_alerts(getattr(self, "price_alerts", [])):
            if isinstance(alert, dict) and alert.get("direction") == "below_ma5":
                codes.append(alert.get("code"))
        config = getattr(self, "strategy_alert_config", {})
        if normalize_strategy_alert_config(config).get("enabled"):
            codes.extend(strategy_daily_request_codes(config))
        return normalize_codes(codes)

    def _intraday_request_codes(self):
        if not getattr(self, "kline_visible", False):
            return []
        return normalize_codes(getattr(self, "checked_codes", []))

    def _refresh_request_codes(self):
        return normalize_codes(
            list(getattr(self, "checked_codes", []))
            + self._alert_request_codes()
            + self._strategy_request_codes()
            + self._market_amount_request_codes()
        )

    def _format_market_amount(self, quote_by_code):
        total = 0.0
        found = False
        for code in self._market_amount_request_codes():
            quote = (quote_by_code or {}).get(code) or {}
            try:
                amount = float(quote.get("amount", 0.0) or 0.0)
            except Exception:
                amount = 0.0
            if amount > 0:
                total += amount
                found = True
        if not found:
            return ""
        return f"沪深成交额估算：{total / 1e8:.2f}亿"

    @staticmethod
    def _eastmoney_secid(code):
        code = normalize_codes([code])
        if not code:
            return ""
        code = code[0]
        market = "1" if code.startswith("sh") else "0"
        return f"{market}.{code[2:]}"

    def _parse_tencent_daily_payload(self, code, payload):
        data = ((payload or {}).get("data") or {}).get(code) or {}
        klines = data.get("qfqday") or data.get("day") or []
        rows = []
        for parts in klines:
            if not isinstance(parts, (list, tuple)) or len(parts) < 6:
                continue
            try:
                rows.append({
                    "date": str(parts[0]),
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]) if len(parts) > 6 else 0.0,
                })
            except Exception:
                continue
        return rows

    def _get_tencent_daily_klines(self, code, limit=20):
        getter = getattr(getattr(self, "_http", None), "get", requests.get)
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{int(limit)},qfq"
        response = getter(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        return self._parse_tencent_daily_payload(code, response.json())

    def _get_eastmoney_daily_klines(self, code, limit=20):
        getter = getattr(getattr(self, "_http", None), "get", requests.get)
        headers = {"Referer": "https://quote.eastmoney.com", "User-Agent": "Mozilla/5.0"}
        secid = self._eastmoney_secid(code)
        if not secid:
            return []
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
            "&fields2=f51,f52,f53,f54,f55,f56,f57"
            f"&klt=101&fqt=1&lmt={int(limit)}&end=20500101"
        )
        response = getter(url, headers=headers, timeout=5)
        payload = response.json()
        klines = (((payload or {}).get("data") or {}).get("klines") or [])
        rows = []
        for raw in klines:
            parts = str(raw).split(",")
            if len(parts) < 6:
                continue
            try:
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]) if len(parts) > 6 else 0.0,
                })
            except Exception:
                continue
        return rows

    @staticmethod
    def _intraday_minute_index(time_text):
        text = str(time_text or "").strip()
        if " " in text:
            text = text.split()[-1]
        parts = text.split(":")
        if len(parts) < 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except Exception:
            return None
        total = hour * 60 + minute
        if 9 * 60 + 30 <= total <= 11 * 60 + 30:
            return total - (9 * 60 + 30)
        if 13 * 60 <= total <= 15 * 60:
            return 121 + total - (13 * 60)
        return None

    def _parse_eastmoney_intraday_payload(self, payload):
        data = (payload or {}).get("data") or {}
        trends = data.get("trends") or []
        points = []
        prev_close = 0.0
        try:
            prev_close = float(data.get("preClose") or data.get("pre_close") or 0.0)
        except Exception:
            prev_close = 0.0
        for raw in trends:
            parts = str(raw or "").split(",")
            if len(parts) < 3:
                continue
            minute = self._intraday_minute_index(parts[0])
            if minute is None:
                continue
            try:
                price = float(parts[2] or 0.0)
            except Exception:
                continue
            if price <= 0:
                continue
            point = {"minute": minute, "price": price}
            if len(parts) > 7:
                try:
                    avg = float(parts[7] or 0.0)
                    if avg > 0:
                        point["avg"] = avg
                except Exception:
                    pass
            points.append(point)
        points.sort(key=lambda item: item["minute"])
        return {"points": points, "prev_close": prev_close, "max_minute": 241}

    def _get_eastmoney_intraday_trend(self, code):
        getter = getattr(getattr(self, "_http", None), "get", requests.get)
        secid = self._eastmoney_secid(code)
        if not secid:
            return {}
        headers = {"Referer": "https://quote.eastmoney.com", "User-Agent": "Mozilla/5.0"}
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
            f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=0&iscca=0&ndays=1"
        )
        response = getter(url, headers=headers, timeout=5)
        return self._parse_eastmoney_intraday_payload(response.json())

    def _get_intraday_trends(self, codes):
        result = {}
        today_provider = getattr(self, "_today", None)
        today = today_provider() if callable(today_provider) else date.today()
        today_key = today.isoformat() if hasattr(today, "isoformat") else str(today)
        cache = getattr(self, "_intraday_trend_cache", {})
        if not isinstance(cache, dict):
            cache = {}
        for code in normalize_codes(codes):
            cached = cache.get(code)
            if cached and cached.get("date") == today_key and time.monotonic() - cached.get("time", 0.0) < 45:
                result[code] = cached.get("trend", {})
                continue
            try:
                trend = self._get_eastmoney_intraday_trend(code)
            except Exception:
                trend = {}
            if trend and trend.get("points"):
                trend["date"] = today_key
                result[code] = trend
                cache[code] = {"date": today_key, "time": time.monotonic(), "trend": trend}
        self._intraday_trend_cache = cache
        return result

    @staticmethod
    def _baostock_code(code):
        code = normalize_codes([code])
        if not code:
            return ""
        code = code[0]
        return f"{code[:2]}.{code[2:]}"

    def _get_baostock_daily_klines(self, code, limit=20):
        import baostock as bs

        bs_code = self._baostock_code(code)
        if not bs_code:
            return []

        end_date = date.today()
        start_date = end_date - timedelta(days=max(30, int(limit) * 3))
        login = bs.login()
        try:
            if getattr(login, "error_code", "0") != "0":
                raise RuntimeError(getattr(login, "error_msg", "baostock login failed"))
            fields = "date,code,open,high,low,close,volume,amount"
            result = bs.query_history_k_data_plus(
                bs_code,
                fields,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="2",
            )
            if getattr(result, "error_code", "0") != "0":
                raise RuntimeError(getattr(result, "error_msg", "baostock query failed"))
            rows = []
            while result.next():
                raw = dict(zip(result.fields, result.get_row_data()))
                try:
                    rows.append({
                        "date": str(raw.get("date") or ""),
                        "open": float(raw.get("open") or 0.0),
                        "close": float(raw.get("close") or 0.0),
                        "high": float(raw.get("high") or 0.0),
                        "low": float(raw.get("low") or 0.0),
                        "volume": float(raw.get("volume") or 0.0),
                        "amount": float(raw.get("amount") or 0.0),
                    })
                except Exception:
                    continue
            return rows[-int(limit):]
        finally:
            try:
                bs.logout()
            except Exception:
                pass

    def _get_daily_klines(self, codes, limit=20):
        daily_by_code = {}
        today_provider = getattr(self, "_today", None)
        today = today_provider() if callable(today_provider) else date.today()
        today_key = today.isoformat() if hasattr(today, "isoformat") else str(today)
        for code in normalize_codes(codes):
            cache = getattr(self, "_daily_kline_cache", {})
            cache_key = (code, int(limit))
            cached = cache.get(cache_key) if isinstance(cache, dict) else None
            if cached and cached.get("date") == today_key and time.monotonic() - cached.get("time", 0.0) < 300:
                daily_by_code[code] = cached.get("rows", [])
                continue

            errors = []
            try:
                rows = self._get_baostock_daily_klines(code, limit)
            except Exception as exc:
                errors.append(f"Baostock:{type(exc).__name__}")
                rows = []
            if not rows:
                try:
                    rows = self._get_tencent_daily_klines(code, limit)
                except Exception as exc:
                    errors.append(f"腾讯:{type(exc).__name__}")
                    rows = []
            if not rows:
                try:
                    rows = self._get_eastmoney_daily_klines(code, limit)
                except Exception as exc:
                    errors.append(f"东财:{type(exc).__name__}")
                    rows = []
            if rows:
                daily_by_code[code] = rows
                if isinstance(cache, dict):
                    cache[cache_key] = {"date": today_key, "time": time.monotonic(), "rows": rows}
                    self._daily_kline_cache = cache
            else:
                daily_by_code[code] = {"error": "日线接口不可用" if errors else "日线数据为空"}
        return daily_by_code

    def _get_refresh_data(self, request_codes):
        row_by_code, sign_by_code, quote_by_code = self._get_price(request_codes)
        daily_by_code = {}
        daily_codes = self._daily_request_codes()
        if daily_codes:
            try:
                limit = 60 if getattr(self, "_kline_chart_code", "") else 20
                daily_by_code = self._get_daily_klines(daily_codes, limit=limit)
            except Exception:
                daily_by_code = {}
        intraday_by_code = {}
        intraday_codes = self._intraday_request_codes()
        if intraday_codes:
            intraday_by_code = self._get_intraday_trends(intraday_codes)
        return row_by_code, sign_by_code, quote_by_code, daily_by_code, intraday_by_code

    def _record_intraday_quote_samples(self, quote_by_code):
        today_provider = getattr(self, "_today", None)
        today = today_provider() if callable(today_provider) else date.today()
        today_key = today.isoformat() if hasattr(today, "isoformat") else str(today)
        now_provider = getattr(self, "_now", None)
        now_dt = now_provider() if callable(now_provider) else datetime.now()
        minute_text = now_dt.strftime("%H:%M") if hasattr(now_dt, "strftime") else ""
        minute = self._intraday_minute_index(minute_text)
        if minute is None:
            return
        cache = getattr(self, "_intraday_sample_cache", {})
        if not isinstance(cache, dict):
            cache = {}
        for code, quote in (quote_by_code or {}).items():
            try:
                price = float((quote or {}).get("price", 0.0))
            except Exception:
                price = 0.0
            if price <= 0:
                continue
            item = cache.get(code)
            if not item or item.get("date") != today_key:
                item = {"date": today_key, "points": []}
            points = [dict(point) for point in item.get("points", []) if isinstance(point, dict)]
            if points and points[-1].get("minute") == minute:
                points[-1] = {"minute": minute, "price": price}
            else:
                points.append({"minute": minute, "price": price})
            item["points"] = points[-242:]
            cache[code] = item
        self._intraday_sample_cache = cache

    def _intraday_payload_for_code(self, code, quote_by_code=None, intraday_by_code=None):
        quote = (quote_by_code or {}).get(code) or {}
        external = (intraday_by_code or {}).get(code) or {}
        points = [dict(point) for point in external.get("points", []) if isinstance(point, dict)]
        today_provider = getattr(self, "_today", None)
        today = today_provider() if callable(today_provider) else date.today()
        today_key = today.isoformat() if hasattr(today, "isoformat") else str(today)
        sample = (getattr(self, "_intraday_sample_cache", {}) or {}).get(code) or {}
        if sample.get("date") == today_key:
            points.extend(dict(point) for point in sample.get("points", []) if isinstance(point, dict))
        try:
            current_price = float(quote.get("price", 0.0) or 0.0)
            opening_price = float(quote.get("open", current_price) or current_price)
            high_price = float(quote.get("high", max(opening_price, current_price)) or current_price)
            low_price = float(quote.get("low", min(opening_price, current_price)) or current_price)
            prev_close = float(quote.get("prev_close", 0.0) or external.get("prev_close", 0.0) or 0.0)
        except Exception:
            return {}
        if current_price > 0:
            now_provider = getattr(self, "_now", None)
            now_dt = now_provider() if callable(now_provider) else datetime.now()
            minute = self._intraday_minute_index(now_dt.strftime("%H:%M") if hasattr(now_dt, "strftime") else "")
            if minute is not None:
                points.append({"minute": minute, "price": current_price})
            if not points:
                points.append({"minute": 0, "price": opening_price if opening_price > 0 else current_price})
                points.append({"minute": 1, "price": current_price})
        deduped = {}
        for point in points:
            try:
                minute = int(point.get("minute"))
                price = float(point.get("price"))
            except Exception:
                continue
            if minute >= 0 and price > 0:
                deduped[minute] = {"minute": minute, "price": price}
        points = [deduped[key] for key in sorted(deduped)]
        if len(points) < 2:
            return {}
        return {
            "type": "intraday",
            "points": points[-242:],
            "prev_close": prev_close,
            "max_minute": 241,
            "ohlc": (opening_price, current_price, high_price, low_price, prev_close),
        }

    def _daily_rows_with_realtime_price(self, daily_by_code, quote_by_code):
        today_provider = getattr(self, "_today", None)
        today = today_provider() if callable(today_provider) else date.today()
        today_key = today.isoformat() if hasattr(today, "isoformat") else str(today)
        result = {}
        for code, rows in (daily_by_code or {}).items():
            if isinstance(rows, dict):
                result[code] = rows
                continue
            merged = [dict(row) for row in (rows or []) if isinstance(row, dict)]
            quote = (quote_by_code or {}).get(code) or {}
            try:
                price = float(quote.get("price", 0.0))
            except Exception:
                price = 0.0
            if price > 0:
                if merged and str(merged[-1].get("date") or "") == today_key:
                    merged[-1]["close"] = price
                    merged[-1]["high"] = max(float(merged[-1].get("high", price) or price), price)
                    merged[-1]["low"] = min(float(merged[-1].get("low", price) or price), price)
                    merged[-1]["realtime"] = True
                else:
                    merged.append({"date": today_key, "open": price, "high": price, "low": price, "close": price, "volume": 0.0, "amount": 0.0, "realtime": True})
            result[code] = merged
        return result

    def _compose_display_rows(self, row_by_code, sign_by_code, alert_states, price_alerts_by_code=None, quote_by_code=None, daily_by_code=None, strategy_states=None, intraday_by_code=None):
        full_rows, meta_rows = [], []
        checked = set(getattr(self, "checked_codes", []))
        alert_rows_added = False
        price_alerts_by_code = price_alerts_by_code or {}
        daily_by_code = daily_by_code or {}
        strategy_by_code = {
            state.get("code"): state
            for state in (strategy_states or [])
            if isinstance(state, dict) and state.get("code")
        }

        for group in getattr(self, "groups", []):
            group_codes = [c for c in group.get("codes", []) if c in checked]
            if not group_codes:
                continue
            full_rows.append(self._message_row(str(group.get("name") or "分组")))
            meta_rows.append({"row_type": "group", "text": str(group.get("name") or "分组")})
            for code in group_codes:
                source_row = row_by_code.get(code)
                meta = dict(sign_by_code.get(code, {}))
                meta["code"] = code
                if source_row is None:
                    source_row = self._empty_stock_row(code)
                    meta["quote_missing"] = True
                strategy_state = strategy_by_code.get(code)
                if strategy_state:
                    meta["strategy"] = True
                    meta["severity"] = strategy_state.get("severity", "neutral")
                if getattr(self, "price_alert_badge_visible", True) and code in price_alerts_by_code:
                    meta["price_alerts"] = price_alerts_by_code[code]
                badges = []
                strategy_triggered = bool(strategy_state and strategy_state.get("triggered"))
                if strategy_triggered:
                    badges.append("策略")
                full_rows.append(self._display_row_with_indicators(source_row, code, daily_by_code, strategy_by_code, badges, quote_by_code, intraday_by_code))
                meta_rows.append(meta)

        market_amount_text = self._format_market_amount(quote_by_code or {})
        if market_amount_text:
            if full_rows:
                full_rows.append(self._separator_row())
                meta_rows.append({"row_type": "separator", "text": ""})
            full_rows.append(self._message_row(market_amount_text))
            meta_rows.append({"row_type": "market_amount", "text": market_amount_text})

        for state in alert_states:
            rule = state.get("rule", {})
            if rule.get("display_mode") != "always" and not state.get("triggered"):
                continue
            if not alert_rows_added:
                full_rows.append(self._separator_row())
                meta_rows.append({"row_type": "separator", "text": ""})
                alert_rows_added = True
            text = f"{rule.get('name', '联动提醒')}：{state.get('status', '')}"
            if state.get("triggered") and state.get("text"):
                text = f"{text}，{state.get('text')}"
            full_rows.append(self._message_row(text))
            meta_rows.append({"row_type": "alert", "text": text, "triggered": bool(state.get("triggered"))})

        if getattr(self, "warning_visible", False) and getattr(self, "warning_text", ""):
            text = str(self.warning_text).strip()
            if full_rows:
                full_rows.append(self._separator_row())
                meta_rows.append({"row_type": "separator", "text": ""})
            full_rows.append(self._message_row(text))
            meta_rows.append({"row_type": "warning", "text": text})

        return full_rows, meta_rows

    def _display_row_with_indicators(self, row, code, daily_by_code=None, strategy_by_code=None, badges=None, quote_by_code=None, intraday_by_code=None):
        result = list(row or [])
        if len(result) < len(self.ALL_HEADERS):
            result.extend(["-"] * (len(self.ALL_HEADERS) - len(result)))
        code_index = self.ALL_HEADERS.index("代码") if "代码" in self.ALL_HEADERS else -1
        name_index = self.ALL_HEADERS.index("名称") if "名称" in self.ALL_HEADERS else -1
        labels = []
        tag_label = self._code_tag_label(code)
        if tag_label:
            labels.append(tag_label)
        labels.extend(str(badge) for badge in (badges or []) if str(badge or "").strip())
        if labels:
            label_text = f"[{'/'.join(labels)}]"
            show_name = self._header_visible_for_indicator("名称")
            target_index = name_index if show_name and 0 <= name_index < len(result) else code_index
            if 0 <= target_index < len(result):
                text = str(result[target_index] or "").strip()
                if text and text != "-":
                    result[target_index] = f"{text} {label_text}"
        daily_rows = (daily_by_code or {}).get(code)
        if "K线" in self.ALL_HEADERS:
            trend_payload = self._intraday_payload_for_code(code, quote_by_code, intraday_by_code)
            if trend_payload:
                result[self.ALL_HEADERS.index("K线")] = {"k": trend_payload}
        ma_values = {
            "MA5": moving_average(daily_rows, 5),
            "MA10": moving_average(daily_rows, 10),
            "MA20": moving_average(daily_rows, 20),
        }
        for header, value in ma_values.items():
            if header in self.ALL_HEADERS:
                result[self.ALL_HEADERS.index(header)] = self._format_strategy_price(value)

        state = (strategy_by_code or {}).get(code) or {}
        strategy_enabled = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {})).get("enabled")
        if strategy_enabled and state:
            profit = state.get("profit_pct")
            status_text = str(state.get("status") or "-")
            daily_label = self._format_strategy_daily_label(state)
            if daily_label and status_text != "-":
                status_text = f"{status_text} | {daily_label}"
            values = {
                "持仓盈亏": "-" if profit is None else f"{float(profit):+.1f}%",
                "止损线": self._format_strategy_price(state.get("stop_price")),
                "策略状态": status_text,
            }
            for header, value in values.items():
                if header in self.ALL_HEADERS:
                    result[self.ALL_HEADERS.index(header)] = value
        else:
            for header in ("持仓盈亏", "止损线", "策略状态"):
                if header in self.ALL_HEADERS:
                    result[self.ALL_HEADERS.index(header)] = "-"
        return result

    def _header_visible_for_indicator(self, header):
        checker = getattr(self, "header_is_visible", None)
        if callable(checker) and "header_is_visible" in getattr(self, "__dict__", {}):
            try:
                return bool(checker(header))
            except Exception:
                return True
        attr_by_header = {"代码": "code_visible", "名称": "name_visible"}
        attr = attr_by_header.get(header)
        if attr and not hasattr(self, attr):
            return True
        if callable(checker):
            try:
                return bool(checker(header))
            except Exception:
                return True
        return True

    def _code_tag_label(self, code):
        tags = getattr(self, "code_tags", {})
        if not isinstance(tags, dict):
            tags = {}
        item = tags.get(code) if isinstance(tags.get(code), dict) else {}
        holding_map = {"hold": "持有", "watch": "观察", "cleared": "清仓"}
        cycle_map = {"short": "短线", "swing": "波段", "long": "长期"}
        priority_map = {"focus": "重点", "normal": "普通", "low": "低优"}
        parts = [
            holding_map.get(item.get("holding"), ""),
            cycle_map.get(item.get("cycle"), ""),
            priority_map.get(item.get("priority"), ""),
        ]
        return "/".join(part for part in parts if part)

    def _compose_strategy_rows(self, strategy_states):
        rows, meta = [], []
        for state in strategy_states:
            profit = state.get("profit_pct")
            rows.append([
                state.get("name") or state.get("code") or "",
                "盈亏 -" if profit is None else f"盈亏 {float(profit):+.1f}%",
                "止损 " + self._format_strategy_price(state.get("stop_price")),
                state.get("status", ""),
            ])
            meta.append({
                "strategy": True,
                "triggered": bool(state.get("triggered")),
                "severity": state.get("severity", "neutral"),
            })
            rows.append([
                "",
                "MA5 " + self._format_strategy_price(state.get("ma5")),
                "MA10 " + self._format_strategy_price(state.get("ma10")),
                "MA20 " + self._format_strategy_price(state.get("ma20")),
            ])
            meta.append({
                "strategy": True,
                "strategy_detail": True,
                "triggered": bool(state.get("triggered")),
                "severity": state.get("severity", "neutral"),
            })
        if not rows:
            rows.append(["策略", "-", "-", "未启用或未添加持仓"])
            meta.append({"strategy": True, "severity": "neutral"})
        return rows, meta

    @staticmethod
    def _format_strategy_price(value):
        try:
            value = float(value)
        except Exception:
            return "-"
        if value <= 0:
            return "-"
        return f"{value:.2f}"

    @staticmethod
    def _format_strategy_daily_label(state):
        date_text = str((state or {}).get("daily_date") or "").strip()
        if not date_text:
            return ""
        if len(date_text) >= 10:
            date_text = date_text[5:10]
        prefix = "实时" if (state or {}).get("daily_realtime") else "日线"
        return f"{prefix}{date_text}"

    def _project_strategy_columns(self, rows, meta):
        headers = ["名称", "盈亏/MA5", "止损/MA10", "状态/MA20"]
        self.model.set_align_right_cols([])
        self.model.set_rows_headers(rows, headers, meta=meta)
        self.model.set_color_scheme(self.default_color, self.fg)
        try:
            self.table.clearSpans()
        except Exception:
            pass
        if self.k_column_visible_index is not None:
            self.table.setItemDelegateForColumn(self.k_column_visible_index, QStyledItemDelegate(self.table))
            self.k_column_visible_index = None
        if self.name_column_visible_index is not None:
            self.table.setItemDelegateForColumn(self.name_column_visible_index, QStyledItemDelegate(self.table))
            self.name_column_visible_index = None
        self._fit_to_contents()

    def _strategy_push_payload(self, text):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        channel = notifications.get("remote_channel", "wecom")
        if channel == "wecom":
            return {"msgtype": "markdown", "markdown": {"content": text}}
        return {
            "source": "StockWidget",
            "type": "strategy_alert",
            "content": text,
        }

    def _send_strategy_push_text(self, text):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        if not notifications.get("remote_push"):
            return False
        url = str(notifications.get("webhook_url") or "").strip()
        if not url:
            return False
        poster = getattr(getattr(self, "_http", None), "post", requests.post)
        poster(url, json=self._strategy_push_payload(text), timeout=5)
        return True

    @staticmethod
    def _strategy_line_label(locked_profit_pct):
        try:
            return "止盈线" if float(locked_profit_pct or 0.0) > 0 else "止损线"
        except Exception:
            return "止损线"

    def _strategy_alert_title_for_state(self, state):
        name = str(state.get("name") or state.get("code") or "策略").strip()
        lock_pct = state.get("locked_profit_pct", 0.0)
        if state.get("stop_line_changed"):
            return f"{name}{self._strategy_line_label(lock_pct)}变化"
        status = str(state.get("status") or "").strip()
        if "止损" in status:
            return f"{name}止损触发"
        if "止盈" in status or "锁盈" in status:
            return f"{name}止盈触发"
        return f"{name}策略触发"

    @staticmethod
    def _strategy_action_lines(state):
        action_lines = []
        for action in state.get("triggered_actions") or []:
            if not isinstance(action, dict):
                continue
            details = action.get("details") if isinstance(action.get("details"), dict) else {}
            label = str(action.get("rule_name") or action.get("message") or action.get("rule_id") or "").strip()
            if not label:
                continue
            value_parts = []
            if details.get("stop_loss_price") is not None:
                value_parts.append(f"止损价{float(details.get('stop_loss_price')):.2f}")
            if details.get("take_profit_price") is not None:
                value_parts.append(f"止盈价{float(details.get('take_profit_price')):.2f}")
            elif details.get("stop_price") is not None:
                value_parts.append(f"策略线{float(details.get('stop_price')):.2f}")
            if details.get("threshold_pct") is not None:
                value_parts.append(f"阈值{float(details.get('threshold_pct')):.1f}%")
            action_text = label if not value_parts else f"{label}：" + "，".join(value_parts)
            action_lines.append(f">{action_text}")
        return action_lines

    def _strategy_push_text_for_state(self, state):
        profit = state.get("profit_pct")
        profit_text = "-" if profit is None else f"{float(profit):+.1f}%"
        lock_pct = float(state.get("locked_profit_pct", 0.0))
        take_profit_price = state.get("take_profit_price")
        if take_profit_price is None and lock_pct > 0:
            take_profit_price = state.get("stop_price")
        stop_loss_price = state.get("stop_loss_price")
        if take_profit_price is None:
            lock_text = "未锁盈"
            stop_text = "-"
        else:
            lock_text = f"{float(take_profit_price):.2f}（锁盈+{lock_pct:.1f}%）"
            stop_text = f"{float(take_profit_price):.2f}"
        stop_loss_text = "-" if stop_loss_price is None else f"{float(stop_loss_price):.2f}"
        change_lines = []
        previous_stop_price = state.get("stop_line_previous_price")
        current_stop_price = state.get("stop_price")
        try:
            if state.get("stop_line_changed") and previous_stop_price is not None and current_stop_price is not None:
                line_label = self._strategy_line_label(lock_pct)
                change_lines.append(f">{line_label}：{float(previous_stop_price):.2f} -> {float(current_stop_price):.2f}")
        except Exception:
            change_lines = []
        lines = [
            f"## {self._strategy_alert_title_for_state(state)}",
            f">标的：{state.get('name') or state.get('code')}",
            f">代码：{state.get('code')}",
            "",
            f">盈亏：{profit_text}",
            f">止损线：{stop_loss_text}",
            f">止盈线：{lock_text}",
        ]
        if change_lines:
            lines.extend(["", ">变动：", *change_lines])
        action_lines = self._strategy_action_lines(state)
        if action_lines:
            lines.extend(["", ">动作：", *action_lines])
        lines.extend(["", f">状态：{state.get('status', '-')}"])
        return "\n".join(lines)

    def _strategy_daily_summary_text(self, strategy_states, now=None):
        now = now or datetime.now()
        lines = [f"## 策略定时摘要", f">时间：{now:%Y-%m-%d %H:%M}"]
        for state in strategy_states or []:
            profit = state.get("profit_pct")
            profit_text = "-" if profit is None else f"{float(profit):+.1f}%"
            stop_loss_text = self._format_strategy_price(state.get("stop_loss_price"))
            take_profit_text = self._format_strategy_price(state.get("take_profit_price"))
            if take_profit_text == "-":
                take_profit_text = self._format_strategy_price(state.get("stop_price") if float(state.get("locked_profit_pct", 0.0)) > 0 else None)
            lines.extend([
                "",
                f">标的：{state.get('name') or state.get('code')}",
                f">代码：{state.get('code')}",
                f">盈亏：{profit_text}",
                f">止损线：{stop_loss_text}",
                f">止盈线：{take_profit_text}",
                f">状态：{state.get('status', '-')}",
            ])
        return "\n".join(lines)

    def _strategy_daily_summary_due_slot(self, now):
        if now.weekday() >= 5:
            return None
        for hour, minute, label in STRATEGY_DAILY_SUMMARY_SLOTS:
            if now.hour != hour:
                continue
            elapsed_minutes = now.minute - minute
            if 0 <= elapsed_minutes < STRATEGY_DAILY_SUMMARY_GRACE_MINUTES:
                return label
        return None

    def _strategy_daily_summary_sent_slots(self, today_key):
        raw = str(getattr(self, "_strategy_daily_summary_sent_date", "") or "")
        if raw == today_key:
            return {label for _, _, label in STRATEGY_DAILY_SUMMARY_SLOTS}
        prefix = f"{today_key}|"
        if not raw.startswith(prefix):
            return set()
        return {part for part in raw[len(prefix):].split(",") if part}

    def _mark_strategy_daily_summary_sent(self, today_key, slot):
        slots = self._strategy_daily_summary_sent_slots(today_key)
        slots.add(slot)
        ordered = [label for _, _, label in STRATEGY_DAILY_SUMMARY_SLOTS if label in slots]
        self._strategy_daily_summary_sent_date = f"{today_key}|{','.join(ordered)}"

    def _strategy_push_recorded_today(self, key, today_key):
        try:
            code, status = key.split("|", 1)
        except ValueError:
            return False
        for item in getattr(self, "strategy_alert_history", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("time") or "")[:10] != today_key:
                continue
            if str(item.get("code") or "") == code and str(item.get("status") or "") == status:
                return True
        return False

    def _send_strategy_daily_summary(self, strategy_states, now=None):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        if not notifications.get("remote_push") or not notifications.get("webhook_url"):
            return False
        now_provider = getattr(self, "_now", None)
        now = now or (now_provider() if callable(now_provider) else datetime.now())
        slot = self._strategy_daily_summary_due_slot(now)
        if not slot:
            return False
        today_key = now.strftime("%Y-%m-%d")
        if slot in self._strategy_daily_summary_sent_slots(today_key):
            return False
        states = list(strategy_states or [])
        if not states:
            return False
        if self._send_strategy_push_text(self._strategy_daily_summary_text(states, now)):
            self._mark_strategy_daily_summary_sent(today_key, slot)
            return True
        return False

    def _send_strategy_pushes(self, strategy_states):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        desktop = notifications.get("desktop_popup")
        remote = notifications.get("remote_push") and bool(notifications.get("webhook_url"))
        if not desktop and not remote:
            return
        sent_keys = getattr(self, "_strategy_push_sent_keys", set())
        sent_at = getattr(self, "_strategy_push_sent_at", {})
        cooldown_seconds = int(notifications.get("push_cooldown_minutes", 30)) * 60
        now_provider = getattr(self, "_now", None)
        now_dt = now_provider() if callable(now_provider) else datetime.now()
        now_ts = now_dt.timestamp() if hasattr(now_dt, "timestamp") else time.time()
        today_key = now_dt.strftime("%Y-%m-%d") if hasattr(now_dt, "strftime") else date.today().strftime("%Y-%m-%d")
        history_changed = False
        for state in strategy_states or []:
            if not state.get("triggered"):
                continue
            key = f"{state.get('code')}|{state.get('status')}"
            if self._is_desktop_alert_ignored(key, now_dt):
                continue
            daily_key = f"{today_key}|{key}"
            if daily_key in sent_keys or self._strategy_push_recorded_today(key, today_key):
                continue
            last_ts = float(sent_at.get(key, 0.0) or 0.0)
            if key in sent_keys and now_ts - last_ts < cooldown_seconds:
                continue
            pushed = False
            if remote:
                try:
                    if self._send_strategy_push_text(self._strategy_push_text_for_state(state)):
                        pushed = True
                except Exception:
                    pass
            if desktop:
                try:
                    self.show_desktop_alert(self._strategy_push_text_for_state(state), ignore_key=key)
                    pushed = True
                except Exception:
                    pass
            if pushed:
                sent_keys.add(daily_key)
                sent_at[key] = now_ts
                self._record_strategy_alert_history(state, now_dt)
                history_changed = True
        self._strategy_push_sent_keys = sent_keys
        self._strategy_push_sent_at = sent_at
        if history_changed:
            self._notify_change()

    def _price_alert_push_text(self, code, alert):
        name = str(alert.get("name") or code or "").strip()
        direction = str(alert.get("direction") or "")
        direction_text = {
            "above": "高于/等于",
            "below": "低于/等于",
            "below_ma5": "低于5日线",
        }.get(direction, direction or "-")
        lines = [
            f"## {name}价格提醒",
            f">标的：{name}",
            f">代码：{code}",
            f">当前价：{float(alert.get('current_price', 0.0)):.3f}",
            f">条件：{direction_text} {float(alert.get('price', 0.0)):.3f}",
        ]
        message = str(alert.get("message") or "").strip()
        if message:
            lines.append(f">提示：{message}")
        return "\n".join(lines)

    def _send_price_alert_pushes(self, price_alerts_by_code):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        if not notifications.get("remote_push") or not notifications.get("webhook_url"):
            return False
        sent_keys = getattr(self, "_price_alert_push_sent_keys", set())
        sent_at = getattr(self, "_price_alert_push_sent_at", {})
        cooldown_seconds = int(notifications.get("push_cooldown_minutes", 30)) * 60
        now_provider = getattr(self, "_now", None)
        now_dt = now_provider() if callable(now_provider) else datetime.now()
        now_ts = now_dt.timestamp() if hasattr(now_dt, "timestamp") else time.time()
        pushed_any = False
        for code, alerts in (price_alerts_by_code or {}).items():
            for alert in alerts or []:
                if not isinstance(alert, dict) or not alert.get("triggered"):
                    continue
                key = f"{code}|{alert.get('direction')}|{float(alert.get('price', 0.0)):.4f}|{alert.get('message', '')}"
                last_ts = float(sent_at.get(key, 0.0) or 0.0)
                if key in sent_keys and now_ts - last_ts < cooldown_seconds:
                    continue
                try:
                    if self._send_strategy_push_text(self._price_alert_push_text(code, alert)):
                        sent_keys.add(key)
                        sent_at[key] = now_ts
                        pushed_any = True
                except Exception:
                    pass
        self._price_alert_push_sent_keys = sent_keys
        self._price_alert_push_sent_at = sent_at
        return pushed_any

    def _prune_expired_price_alerts(self, now=None):
        now_provider = getattr(self, "_now", None)
        now = now or (now_provider() if callable(now_provider) else datetime.now())
        today = now.date() if isinstance(now, datetime) else now
        active_alerts = []
        changed = False
        for alert in normalize_price_alerts(getattr(self, "price_alerts", [])):
            if price_alert_is_expired(alert, today):
                changed = True
                continue
            active_alerts.append(alert)
        if changed:
            self.price_alerts = active_alerts
        return changed

    def _record_strategy_alert_history(self, state, now=None):
        now = now or datetime.now()
        time_text = now.strftime("%Y-%m-%d %H:%M") if hasattr(now, "strftime") else str(now)
        code = normalize_code_or_none(state.get("code")) or str(state.get("code") or "")
        item = {
            "time": time_text,
            "code": code,
            "name": str(state.get("name") or code).strip(),
            "status": str(state.get("status") or "").strip(),
            "severity": str(state.get("severity") or "neutral").strip(),
        }
        history = [item]
        for old in getattr(self, "strategy_alert_history", []):
            if old.get("code") == item["code"] and old.get("status") == item["status"] and old.get("time") == item["time"]:
                continue
            history.append(old)
            if len(history) >= 50:
                break
        self.strategy_alert_history = history

    def _desktop_alert_ignore_date(self, now=None):
        now_provider = getattr(self, "_now", None)
        now = now or (now_provider() if callable(now_provider) else datetime.now())
        return now.strftime("%Y-%m-%d") if hasattr(now, "strftime") else str(now)[:10]

    def _is_desktop_alert_ignored(self, key, now=None):
        if not key:
            return False
        ignored = getattr(self, "_desktop_alert_ignored_today", {})
        return ignored.get(str(key)) == self._desktop_alert_ignore_date(now)

    def _ignore_desktop_alert_today(self, key, toast=None):
        if key:
            ignored = dict(getattr(self, "_desktop_alert_ignored_today", {}) or {})
            ignored[str(key)] = self._desktop_alert_ignore_date()
            self._desktop_alert_ignored_today = ignored
            self._notify_change()
        if toast is not None:
            self._close_alert_toast(toast)

    def _create_alert_toast(self, plain, ignore_key=None):
        toast = QFrame(self)
        toast.setObjectName("alert_toast")
        toast.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        layout = QHBoxLayout(toast)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)
        label = QLabel(toast)
        label.setObjectName("alert_toast_label")
        label.setWordWrap(True)
        label.setMinimumWidth(220)
        label.setMaximumWidth(340)
        ignore_btn = QPushButton("忽略今日", toast)
        ignore_btn.setObjectName("alert_toast_ignore")
        ignore_btn.setFixedHeight(24)
        close_btn = QPushButton("×", toast)
        close_btn.setObjectName("alert_toast_close")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(lambda _checked=False, item=toast: self._close_alert_toast(item))
        ignore_btn.clicked.connect(lambda _checked=False, key=ignore_key, item=toast: self._ignore_desktop_alert_today(key, item))
        layout.addWidget(label, 1)
        if ignore_key:
            layout.addWidget(ignore_btn, 0, Qt.AlignTop)
        else:
            ignore_btn.hide()
        layout.addWidget(close_btn, 0, Qt.AlignTop)
        toast.setStyleSheet(
            "QFrame#alert_toast{background:#1f2937;color:#f9fafb;border:1px solid #60a5fa;border-radius:6px;}"
            "QLabel#alert_toast_label{color:#f9fafb;font-size:12px;}"
            "QPushButton#alert_toast_ignore{background:#374151;color:#f9fafb;border:1px solid #4b5563;border-radius:3px;padding:1px 8px;font-size:12px;}"
            "QPushButton#alert_toast_ignore:hover{background:#4b5563;}"
            "QPushButton#alert_toast_close{background:transparent;color:#f9fafb;border:none;font-size:16px;font-weight:700;}"
            "QPushButton#alert_toast_close:hover{background:#374151;border-radius:3px;}"
        )
        toast._message_label = label
        toast._ignore_button = ignore_btn
        toast._ignore_key = ignore_key
        label.setText(plain)
        toast.hide()
        return toast

    def _close_alert_toast(self, toast):
        toasts = list(getattr(self, "_alert_toasts", []))
        if toast in toasts:
            toasts.remove(toast)
            self._alert_toasts = toasts
        try:
            toast.hide()
            toast.deleteLater()
        except Exception:
            pass
        self._relayout_alert_toasts()

    def _relayout_alert_toasts(self):
        toasts = [toast for toast in getattr(self, "_alert_toasts", []) if toast is not None]
        if not toasts:
            self._alert_toasts = []
            return
        geo = self.geometry()
        screen = QApplication.screenAt(geo.center()) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        top_limit = available.top() + 8 if available is not None else 8
        bottom_y = geo.y() - 8
        for toast in reversed(toasts):
            toast.adjustSize()
            x = geo.x() + max(0, geo.width() - toast.width())
            y = max(top_limit, bottom_y - toast.height())
            toast.move(x, y)
            bottom_y = y - 6

    @staticmethod
    def _compact_desktop_alert_text(text):
        lines = []
        for raw in str(text or "").splitlines():
            clean = str(raw or "").strip()
            if clean.startswith("## "):
                clean = clean[3:].strip()
            if clean.startswith(">"):
                clean = clean[1:].strip()
            if clean:
                lines.append(clean)
        if not lines:
            return ""
        picked = [lines[0]]
        for line in lines[1:]:
            if line.startswith(("标的：", "代码：", "盈亏：", "成本价：", "止损线：", "止盈线：", "变动：", "状态：")):
                picked.append(line)
            if len(picked) >= 6:
                break
        return "\n".join(picked)

    def show_desktop_alert(self, text, ignore_key=None):
        notifications = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))["notifications"]
        if not notifications.get("desktop_popup"):
            return
        if ignore_key and self._is_desktop_alert_ignored(ignore_key):
            return
        plain = self._compact_desktop_alert_text(text)
        toast = self._create_alert_toast(plain, ignore_key=ignore_key)
        toasts = list(getattr(self, "_alert_toasts", []))
        toasts.append(toast)
        while len(toasts) > 3:
            old = toasts.pop(0)
            try:
                old.hide()
                old.deleteLater()
            except Exception:
                pass
        self._alert_toasts = toasts
        self._relayout_alert_toasts()
        toast.show()

    def send_strategy_push_test(self):
        self._send_strategy_push_text("## 策略测试推送\n>状态：策略远程推送已配置")

    def _project_columns(self, full_rows, sign_data):
        # 从 ALL_HEADERS 中按显示顺序筛选已启用的列
        cols = [i for i, h in enumerate(self.ALL_HEADERS) if self.header_is_visible(h)]
        if not cols:
            cols = [1]
        elif "代码" in self.ALL_HEADERS and "名称" in self.ALL_HEADERS:
            code_idx = self.ALL_HEADERS.index("代码")
            name_idx = self.ALL_HEADERS.index("名称")
            if code_idx not in cols and name_idx not in cols:
                cols.insert(0, name_idx)
        headers = [self.ALL_HEADERS[i] for i in cols]

        proj_rows, proj_meta = [], []
        for r, row in enumerate(full_rows):
            meta = sign_data[r] if r < len(sign_data) else {}
            if meta.get("row_type"):
                projected = [""] * len(cols)
                projected[0] = meta.get("text", "")
                proj_rows.append(projected)
            else:
                proj_rows.append([row[i] for i in cols])
            proj_meta.append(meta)

        # 右对齐：除了名称、K线、卖一外的所有列都右对齐
        right_cols = [i for i, h in enumerate(headers) if h not in ("名称", "K线", "卖一")]
        self.model.set_align_right_cols(right_cols)
        self.model.set_rows_headers(proj_rows, headers, meta=proj_meta)
        self.model.set_color_scheme(self.default_color, self.fg)

        try:
            self.table.clearSpans()
            if len(headers) > 1:
                for r, meta in enumerate(proj_meta):
                    if meta.get("row_type"):
                        self.table.setSpan(r, 0, 1, len(headers))
        except Exception:
            pass

        if "K线" in headers:
            col = headers.index("K线")
            if self.k_column_visible_index is not None and self.k_column_visible_index != col:
                self.table.setItemDelegateForColumn(self.k_column_visible_index, QStyledItemDelegate(self.table))
            self.k_column_visible_index = col
            self.k_delegate.update_scheme(self.default_color, self.fg)
            self.k_delegate.set_point_size(self.font.pointSize())
            self.table.setItemDelegateForColumn(col, self.k_delegate)
        else:
            if self.k_column_visible_index is not None:
                self.table.setItemDelegateForColumn(self.k_column_visible_index, QStyledItemDelegate(self.table))
                self.k_column_visible_index = None

        if "名称" in headers:
            col = headers.index("名称")
            if self.name_column_visible_index is not None and self.name_column_visible_index != col:
                self.table.setItemDelegateForColumn(self.name_column_visible_index, QStyledItemDelegate(self.table))
            self.name_column_visible_index = col
            self.name_delegate.update_scheme(self.fg)
            self.table.setItemDelegateForColumn(col, self.name_delegate)
        else:
            if self.name_column_visible_index is not None:
                self.table.setItemDelegateForColumn(self.name_column_visible_index, QStyledItemDelegate(self.table))
                self.name_column_visible_index = None

        self._fit_to_contents()

    def _refresh_from_function(self, force=False):
        if getattr(self, "_refresh_future", None) is not None and not self._refresh_future.done():
            self._refresh_again_requested = True
            self._refresh_again_force = bool(getattr(self, "_refresh_again_force", False) or force)
            return
        if not force and not self._is_market_fetch_time():
            self._check_strategy_daily_summary()
            return
        try:
            request_codes = self._refresh_request_codes()
            self._refresh_previous_quotes = dict(getattr(self, "_latest_quotes", {}))
            executor = getattr(self, "_refresh_executor", None)
            if executor is None:
                result = self._get_refresh_data(request_codes)
                if len(result) == 4:
                    row_by_code, sign_by_code, quote_by_code, daily_by_code = result
                    intraday_by_code = {}
                else:
                    row_by_code, sign_by_code, quote_by_code, daily_by_code, intraday_by_code = result
                self._apply_refresh_result(row_by_code, sign_by_code, quote_by_code, self._refresh_previous_quotes, daily_by_code, intraday_by_code)
                return
            self._refresh_future = executor.submit(self._get_refresh_data, request_codes)
            self._poll_refresh_future()
        except Exception as e:
            self._refresh_future = None
            try:
                import requests as _req
                if isinstance(e, _req.exceptions.RequestException):
                    self._show_error(_req.exceptions.RequestException())
                else:
                    self._show_error(str(e))
            except Exception:
                self._show_error(str(e))
            return

    def _is_market_fetch_time(self, now=None):
        now_provider = getattr(self, "_now", None)
        now = now or (now_provider() if callable(now_provider) else datetime.now())
        if hasattr(now, "weekday") and now.weekday() >= 5:
            return False
        current_minutes = int(now.hour) * 60 + int(now.minute)
        return 9 * 60 <= current_minutes <= 15 * 60

    def _strategy_summary_states(self):
        states = list(getattr(self, "_latest_strategy_states", []) or [])
        if states:
            return states
        config = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))
        if not config.get("enabled"):
            return []
        quotes = dict(getattr(self, "_latest_quotes", {}) or {})
        for position in config.get("positions", []):
            code = position.get("code")
            if code and code not in quotes:
                quotes[code] = {"name": self.code_names.get(code, code), "price": 0.0}
        return evaluate_strategy_alerts(config, quotes, {})

    def _check_strategy_daily_summary(self):
        config = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))
        if not config.get("enabled"):
            return False
        return self._send_strategy_daily_summary(self._strategy_summary_states())

    def _poll_refresh_future(self):
        future = getattr(self, "_refresh_future", None)
        if future is None:
            return
        if not future.done():
            QTimer.singleShot(30, self._poll_refresh_future)
            return

        self._refresh_future = None
        try:
            result = future.result()
            if len(result) == 4:
                row_by_code, sign_by_code, quote_by_code, daily_by_code = result
                intraday_by_code = {}
            else:
                row_by_code, sign_by_code, quote_by_code, daily_by_code, intraday_by_code = result
            self._apply_refresh_result(
                row_by_code,
                sign_by_code,
                quote_by_code,
                getattr(self, "_refresh_previous_quotes", {}),
                daily_by_code,
                intraday_by_code,
            )
        except Exception as e:
            try:
                import requests as _req
                if isinstance(e, _req.exceptions.RequestException):
                    self._show_error(_req.exceptions.RequestException())
                else:
                    self._show_error(str(e))
            except Exception:
                self._show_error(str(e))

    def _apply_refresh_result(self, row_by_code, sign_by_code, quote_by_code, previous_quotes, daily_by_code=None, intraday_by_code=None):
        alert_states = evaluate_alert_rules(self.alert_rules, quote_by_code, previous_quotes)
        self._record_intraday_quote_samples(quote_by_code)
        daily_by_code = self._daily_rows_with_realtime_price(daily_by_code or {}, quote_by_code)
        self._latest_daily_by_code = dict(daily_by_code or {})
        dialog = getattr(self, "_kline_chart_dialog", None)
        if dialog is not None and dialog.isVisible() and getattr(dialog, "code", ""):
            chart_value = self._latest_daily_by_code.get(dialog.code)
            chart_rows = chart_value if isinstance(chart_value, list) else []
            status_text = chart_value.get("error", "") if isinstance(chart_value, dict) else ""
            dialog.chart.set_rows(chart_rows, status_text=status_text)
        price_alerts_changed = self._prune_expired_price_alerts()
        price_alert_states = evaluate_price_alerts(self.price_alerts, quote_by_code, daily_by_code or {})
        self._latest_price_alert_states = price_alert_states
        price_alert_pushed = self._send_price_alert_pushes(price_alert_states)
        config = normalize_strategy_alert_config(getattr(self, "strategy_alert_config", {}))
        if config.get("enabled"):
            updated_config, strategy_changed = update_strategy_position_state(self.strategy_alert_config, quote_by_code)
            if strategy_changed:
                self.strategy_alert_config = updated_config
            strategy_states = evaluate_strategy_alerts(self.strategy_alert_config, quote_by_code, daily_by_code or {})
            self._latest_strategy_states = list(strategy_states or [])
            self._send_strategy_pushes(strategy_states)
            daily_summary_sent = self._send_strategy_daily_summary(strategy_states)
        else:
            strategy_changed = False
            daily_summary_sent = False
            strategy_states = []
            self._latest_strategy_states = []
        full_rows, sign = self._compose_display_rows(row_by_code, sign_by_code, alert_states, price_alert_states, quote_by_code, daily_by_code, strategy_states, intraday_by_code)
        self._latest_quotes = quote_by_code
        learned_names = False
        for code, quote in (quote_by_code or {}).items():
            name = str((quote or {}).get("name") or "").strip()
            if name and self.code_names.get(code) != name:
                self.code_names[code] = name
                learned_names = True
        if learned_names or strategy_changed or daily_summary_sent or price_alert_pushed or price_alerts_changed:
            self._notify_change()

        try:
            self._clear_error()
        except Exception:
            pass
        self._project_columns(full_rows, sign)
        if getattr(self, "_refresh_again_requested", False):
            force_again = bool(getattr(self, "_refresh_again_force", False))
            self._refresh_again_requested = False
            self._refresh_again_force = False
            QTimer.singleShot(0, lambda: self._refresh_from_function(force=force_again))

    # ----- 应用设置 -----
    def set_groups(self, groups):
        self.groups = normalize_groups(groups, self.codes)
        self.codes = flatten_group_codes(self.groups)
        self.checked_codes = [c for c in self.checked_codes if c in self.codes]
        if not self.checked_codes:
            self.checked_codes = list(self.codes)
        self.code_tags = {code: tags for code, tags in getattr(self, "code_tags", {}).items() if code in self.codes}
        self._notify_change()
        self._refresh_from_function(force=True)

    def set_codes(self, codes_list):
        new = normalize_codes(codes_list)
        if not new: 
            new = ["sh000001"]
        self.codes = new
        self.groups = [{"name": "默认", "codes": list(new)}]
        self.code_tags = {code: tags for code, tags in getattr(self, "code_tags", {}).items() if code in self.codes}
        self._notify_change()
        self._refresh_from_function(force=True)

    def set_checked_codes(self, codes_list):
        new = [c for c in normalize_codes(codes_list) if c in self.codes]
        if not new: 
            new = [self.codes[0] if self.codes else "sh000001"]
        self.checked_codes = new
        self._notify_change()
        self._refresh_from_function(force=True)

    def set_alert_rules(self, rules):
        self.alert_rules = normalize_alert_rules(rules)
        self._notify_change()
        self._refresh_from_function()

    def set_price_alerts(self, alerts):
        self.price_alerts = normalize_price_alerts(alerts)
        self._notify_change()
        self._refresh_from_function()

    def set_strategy_alert_config(self, config):
        self.strategy_alert_config = normalize_strategy_alert_config(config)
        self._daily_kline_cache = {}
        self._notify_change()
        self._refresh_from_function(force=not self._is_market_fetch_time())

    def set_panel_display_mode(self, mode):
        self.panel_display_mode = "quotes"

    def set_warning(self, visible: bool, text: str):
        self.warning_visible = bool(visible)
        self.warning_text = str(text or "").strip() or DEFAULT_WARNING_TEXT
        self._notify_change()
        self._refresh_from_function()

    def set_market_amount_visible(self, visible: bool):
        self.market_amount_visible = bool(visible)
        self._notify_change()
        self._refresh_from_function()

    def set_price_alert_badge_visible(self, visible: bool):
        self.price_alert_badge_visible = bool(visible)
        self._last_fit_signature = None
        self._notify_change()
        self._refresh_from_function(force=True)

    def set_data_source(self, data_source):
        self.data_source = self._normalize_data_source(data_source)
        self._notify_change()
        self._refresh_from_function()

    def set_flag(self, idx, checked: bool):
        """设置指标显示标志。idx 可以是整数索引（向后兼容）或列标题字符串"""
        # 兼容老版本：若传整数索引，转为列标题
        if isinstance(idx, int):
            if 0 <= idx < len(self.ALL_HEADERS):
                header = self.ALL_HEADERS[idx]
            else:
                return
        else:
            header = str(idx)
            if header not in self.ALL_HEADERS:
                return
        
        checked = bool(checked)
        prev = None
        try:
            if header == "代码":
                prev = bool(getattr(self, 'code_visible', False)); self.code_visible = checked
            elif header == "名称":
                prev = bool(getattr(self, 'name_visible', False)); self.name_visible = checked
            elif header == "现价":
                prev = bool(getattr(self, 'price_visible', False)); self.price_visible = checked
            elif header == "涨跌值":
                prev = bool(getattr(self, 'change_visible', False)); self.change_visible = checked
            elif header == "涨跌幅":
                prev = bool(getattr(self, 'change_pct_visible', False)); self.change_pct_visible = checked
            elif header in ("买一", "卖一"):
                prev = bool(getattr(self, 'b1s1_visible', False)); self.b1s1_visible = checked
            elif header == "委比":
                prev = bool(getattr(self, 'commi_visible', False)); self.commi_visible = checked
            elif header == "成交量":
                prev = bool(getattr(self, 'vol_visible', False)); self.vol_visible = checked
            elif header == "成交额":
                prev = bool(getattr(self, 'amount_visible', False)); self.amount_visible = checked
            elif header == "均价":
                prev = bool(getattr(self, 'avg_visible', False)); self.avg_visible = checked
            elif header == "K线":
                prev = bool(getattr(self, 'kline_visible', False)); self.kline_visible = checked
            elif header == "MA5":
                prev = bool(getattr(self, 'ma5_visible', False)); self.ma5_visible = checked; self._daily_kline_cache = {}
            elif header == "MA10":
                prev = bool(getattr(self, 'ma10_visible', False)); self.ma10_visible = checked; self._daily_kline_cache = {}
            elif header == "MA20":
                prev = bool(getattr(self, 'ma20_visible', False)); self.ma20_visible = checked; self._daily_kline_cache = {}
            elif header == "持仓盈亏":
                prev = bool(getattr(self, 'strategy_profit_visible', False)); self.strategy_profit_visible = checked
            elif header == "止损线":
                prev = bool(getattr(self, 'strategy_stop_visible', False)); self.strategy_stop_visible = checked
            elif header == "策略状态":
                prev = bool(getattr(self, 'strategy_status_visible', False)); self.strategy_status_visible = checked
        except Exception:
            prev = None

        if prev is None or prev == checked:
            # 如果状态没有变化仍然返回（避免额外刷新）
            if prev == checked:
                return
        self._notify_change()
        self._refresh_from_function()

    def set_code_type(self, pure_num: bool):
        self.short_code = bool(pure_num)
        self._notify_change()
        self._refresh_from_function()

    def set_name_length(self, name_len: int):
        if name_len >=0:
            self.name_length = name_len
            self._notify_change()
            self._refresh_from_function()

    def set_b1s1_display(self, mode: str):
        """mode: 'qty' | 'price' | 'both'"""
        if mode not in ("qty", "price", "both"):
            return
        self.b1s1_display = mode
        self._notify_change()
        self._refresh_from_function()

    def set_header_visible(self, vis: bool):
        self.header_visible = bool(vis)
        self.table.horizontalHeader().setVisible(self.header_visible)
        self._notify_change()
        self._defer_fit()

    def set_grid_visible(self, vis: bool):
        self.grid_visible = bool(vis)
        self.apply_style()
        self._notify_change()

    def set_refresh_interval(self, seconds: int):
        if seconds in {1,2,3,5,10,15,30,60}:
            self.refresh_seconds = seconds
            self.timer.setInterval(seconds*1000)
            self._notify_change()

    def set_fg_color(self, c: QColor):
        if isinstance(c, QColor) and c.isValid():
            self.fg = QColor(c)
            self.apply_style()
            self._notify_change()

    def set_bg_rgb_keep_alpha(self, c: QColor):
        if isinstance(c, QColor) and c.isValid():
            c2 = QColor(c)
            c2.setAlpha(self.bg.alpha())
            self.bg = c2
            self.apply_style()
            self._notify_change()

    def set_bg_alpha_percent(self, percent_0_100: int):
        p = max(0, min(100, int(percent_0_100)))
        self.bg.setAlpha(int(round(p*2.55)))
        self.apply_style()
        self._notify_change()

    def set_window_opacity_percent(self, percent_20_100: int):
        p = max(20, min(100, int(percent_20_100)))
        self.setWindowOpacity(p/100.0)
        self._defer_fit()
        self._notify_change()

    def set_font_size(self, pt: int):
        pt = max(8, min(15, int(pt)))
        self.font.setPointSize(pt)
        self.k_delegate.set_point_size(pt)
        self.apply_style()
        self._notify_change()
        self.table.viewport().update()
        self._defer_fit()

    def set_font_family(self, family: str):
        if family and family != self.font.family():
            self.font.setFamily(family)
            self.apply_style()
            self._notify_change()

    def set_line_extra(self, px: int):
        self.line_extra_px = max(0, int(px))
        self.apply_style()
        self._defer_fit()
        self._notify_change()

    def set_default_color(self, enabled: bool):
        self.default_color = bool(enabled)
        self.model.set_color_scheme(self.default_color, self.fg)
        self.k_delegate.update_scheme(self.default_color, self.fg)
        self.apply_style()
        self._notify_change()
        self._defer_fit()

    def set_start_on_boot(self, enabled: bool):
        self.start_on_boot = bool(enabled)
        self._notify_change()
    
    # ----- 交互 -----
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        sub_cols = QMenu("显示指标", menu)
        self._populate_display_indicator_menu(sub_cols)
        menu.addMenu(sub_cols)

        act_header = QAction("显示表头", menu, checkable=True)
        act_header.setChecked(self.header_visible)
        act_header.toggled.connect(self.set_header_visible)
        menu.addAction(act_header)

        act_grid = QAction("显示网格",menu, checkable=True)
        act_grid.setChecked(self.grid_visible)
        act_grid.toggled.connect(self.set_grid_visible)
        menu.addAction(act_grid)

        act_color = QAction("默认颜色", menu, checkable=True)
        act_color.setChecked(self.default_color)
        act_color.toggled.connect(self.set_default_color)
        menu.addAction(act_color)

        menu.addSeparator()
        act_open_settings = QAction("设置…", menu)
        act_open_settings.triggered.connect(self._open_settings_cb)
        menu.addAction(act_open_settings)

        menu.addSeparator()
        menu.addAction(QAction("隐藏浮窗", menu, triggered=self.hide))
        menu.exec(event.globalPos())

    def _populate_display_indicator_menu(self, sub_cols):
        for name in self.ALL_HEADERS:
            if name == "卖一":
                continue
            if name == "买一":
                act = QAction("买一/卖一", sub_cols, checkable=True)
                act.setChecked(self.header_is_visible("买一"))
                act.toggled.connect(partial(self.set_flag, "买一"))
                sub_cols.addAction(act)
                continue
            act = QAction(name, sub_cols, checkable=True)
            act.setChecked(self.header_is_visible(name))
            act.toggled.connect(partial(self.set_flag, name))
            sub_cols.addAction(act)
        sub_cols.addSeparator()
        act_badge = QAction("价格提醒标识", sub_cols, checkable=True)
        act_badge.setChecked(bool(getattr(self, "price_alert_badge_visible", True)))
        act_badge.toggled.connect(self.set_price_alert_badge_visible)
        sub_cols.addAction(act_badge)

    def _kline_code_at_event(self, obj, event):
        if obj is not getattr(self.table, "viewport", lambda: None)():
            return ""
        try:
            index = self.table.indexAt(event.position().toPoint())
            if not index.isValid() or index.column() >= len(self.model._headers):
                return ""
            if self.model._headers[index.column()] != "K线":
                return ""
            meta = self.model._row_meta[index.row()] if index.row() < len(self.model._row_meta) else {}
            if meta.get("row_type"):
                return ""
            return normalize_code_or_none(meta.get("code")) or ""
        except Exception:
            return ""

    def _open_kline_chart(self, code):
        code = normalize_code_or_none(code)
        if not code:
            return False
        quote_data = (getattr(self, "_latest_quotes", {}) or {}).get(code) or {}
        name = str(quote_data.get("name") or self.code_names.get(code) or code)
        chart_value = (getattr(self, "_latest_daily_by_code", {}) or {}).get(code)
        chart_rows = chart_value if isinstance(chart_value, list) else []
        status_text = chart_value.get("error", "") if isinstance(chart_value, dict) else ""
        if not chart_rows and not status_text:
            status_text = "正在加载日线数据..."

        dialog = getattr(self, "_kline_chart_dialog", None)
        if dialog is None:
            dialog = KLineChartDialog(self)
            dialog.finished.connect(self._on_kline_chart_closed)
            self._kline_chart_dialog = dialog
        self._kline_chart_code = code
        self.suspend_keep_top(8.0)
        dialog.show_stock(code, name, chart_rows, status_text=status_text)
        if not chart_rows:
            self._refresh_from_function(force=True)
        return True

    def _on_kline_chart_closed(self, *_args):
        self._kline_chart_code = ""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setFocus(Qt.MouseFocusReason)

    def mouseMoveEvent(self, e):
        if getattr(self, "_drag_pos", None) and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            self._ensure_on_top()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = None
            self._ensure_on_top()
            self._notify_change()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = None
            self.hide()

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonDblClick and hasattr(ev, "button") and ev.button() == Qt.LeftButton:
            code = self._kline_code_at_event(obj, ev)
            if code:
                self._drag_pos = None
                self._open_kline_chart(code)
                return True
            self._drag_pos = None
            self.hide()
            return True
        if ev.type() == QEvent.MouseButtonPress and hasattr(ev, "button") and ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_press_global = ev.globalPosition().toPoint()
            self._drag_moved = False
            self._pressed_kline_code = self._kline_code_at_event(obj, ev)
            self.setFocus(Qt.MouseFocusReason)
            return True
        if ev.type() == QEvent.MouseMove and hasattr(ev, "buttons") and (ev.buttons() & Qt.LeftButton) and getattr(self, "_drag_pos", None):
            press_pos = getattr(self, "_drag_press_global", None)
            if press_pos is not None:
                distance = (ev.globalPosition().toPoint() - press_pos).manhattanLength()
                if distance < QApplication.startDragDistance():
                    return True
            self._drag_moved = True
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            return True
        if ev.type() == QEvent.MouseButtonRelease and hasattr(ev, "button") and ev.button() == Qt.LeftButton:
            released_code = self._kline_code_at_event(obj, ev)
            pressed_code = getattr(self, "_pressed_kline_code", "")
            moved = bool(getattr(self, "_drag_moved", False))
            self._drag_pos = None
            self._drag_press_global = None
            self._drag_moved = False
            self._pressed_kline_code = ""
            if not moved and pressed_code and pressed_code == released_code:
                self._open_kline_chart(pressed_code)
            elif moved:
                self._notify_change()
            return True
        return QWidget.eventFilter(self, obj, ev)

    def closeEvent(self, event): 
        event.ignore()
        self.hide()

    def shutdown_background(self):
        try:
            executor = getattr(self, "_refresh_executor", None)
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
                self._refresh_executor = None
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if self.timer and not self.timer.isActive(): 
            self.timer.start()
        if self._keep_top_timer and not self._keep_top_timer.isActive():
            self._keep_top_timer.start()
        self._defer_fit()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._keep_top_timer and self._keep_top_timer.isActive():
            self._keep_top_timer.stop()

    def _ensure_on_top(self):
        if not self.isVisible():
            return
        if time.monotonic() < getattr(self, "_suspend_keep_top_until", 0.0):
            return
        try:
            aw = QApplication.activeWindow()
            popup = QApplication.activePopupWidget()
            if aw is not None and aw is not self and not self.isAncestorOf(aw):
                return
            if popup is not None and popup is not self and not self.isAncestorOf(popup):
                return
        except Exception:
            pass
        self.raise_()

    def suspend_keep_top(self, seconds: float = 6.0):
        try:
            self._suspend_keep_top_until = max(
                getattr(self, "_suspend_keep_top_until", 0.0),
                time.monotonic() + max(0.5, float(seconds)),
            )
        except Exception:
            pass

    def _register_hotkey(self):
        try:
            keyboard.remove_all_hotkeys()
        except Exception:
            pass
        keyboard.add_hotkey(self.hotkey.lower(), lambda: self.hotkey_triggered.emit())

    def update_hotkey(self, new_hotkey: str):
        self.hotkey = new_hotkey.strip()
        self._register_hotkey()

    def toggle_win(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
