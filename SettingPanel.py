import json
import os, re
from datetime import date, datetime
from functools import partial

from PySide6.QtCore import Qt, QSize, QTimer, QEvent
from PySide6.QtGui import QColor, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QPushButton, QSlider,
    QGroupBox, QLabel, QColorDialog, QComboBox, QAbstractItemView,
    QCheckBox, QListWidget, QListWidgetItem, QKeySequenceEdit, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QDoubleSpinBox, QSpinBox, QScrollArea, QRadioButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from WidgetPanel import FloatLabel
from StockLogic import (
    DEFAULT_WARNING_TEXT,
    default_alert_rule,
    default_price_alert,
    default_turtle_action_rules,
    normalize_alert_rule,
    normalize_alert_rules,
    normalize_alert_target,
    normalize_code_or_none,
    normalize_codes,
    normalize_price_alert,
    normalize_price_alerts,
    normalize_strategy_action_rule,
    normalize_strategy_alert_config,
    normalize_strategy_position,
    strategy_rules_for_position,
    strategy_stop_price,
)

class SettingsDialog(QDialog):
    def __init__(self, win: FloatLabel, parent: QWidget, app=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.win = win
        self.app = app
        self.setModal(False)

        main = QHBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)
        self.tabs = QTabWidget()
        main.addWidget(self.tabs)

        self.tab_sizes = {
            0: QSize(430, 620),
            1: QSize(560, 560),
            2: QSize(620, 700),
            3: QSize(360, 350),
            4: QSize(300, 220),
            5: QSize(520, 240),
        }
        self._apply_tab_size(0)

        # ---- 第一页 ----
        tab_0 = QWidget()
        code_settings = QVBoxLayout(tab_0)

        # 1.自选列表
        g_codes = QGroupBox("自选列表")
        g_codes.setContentsMargins(3,12,3,6)
        lay_codes = QHBoxLayout(g_codes)
        lay_codes.setSpacing(6)
        # 1.1 分组代码树
        self.tree_codes = QTreeWidget()
        self.tree_codes.setHeaderHidden(True)
        self.tree_codes.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
        self.tree_codes.setMinimumWidth(300)
        self.tree_codes.setMinimumHeight(250)
        self.tree_codes.setIndentation(18)
        self._load_code_tree()
        # 1.2 操作按钮
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        self.btn_add = QPushButton("添加")
        self.btn_add.setFixedWidth(60)
        self.btn_add_group = QPushButton("分组")
        self.btn_add_group.setFixedWidth(60)
        self.btn_del = QPushButton("删除")
        self.btn_del.setFixedWidth(60)
        self.btn_up  = QPushButton("上移")
        self.btn_up.setFixedWidth(60)
        self.btn_dn  = QPushButton("下移")
        self.btn_dn.setFixedWidth(60)
        self.btn_code_to_alert = QPushButton("设提醒")
        self.btn_code_to_alert.setFixedWidth(60)
        self.btn_code_to_alert.setVisible(False)
        self.btn_code_to_alert.setToolTip("用当前选中的自选股创建或打开价格提醒")
        self.btn_code_to_strategy = QPushButton("设策略")
        self.btn_code_to_strategy.setFixedWidth(60)
        self.btn_code_to_strategy.setToolTip("用当前选中的自选股创建或打开持仓策略")
        for b in (self.btn_add, self.btn_add_group, self.btn_del, self.btn_up, self.btn_dn):
            btn_col.addWidget(b)
        btn_col.addSpacing(8)
        btn_col.addWidget(self.btn_code_to_strategy)
        btn_col.addStretch(1)

        self.cmb_code_holding = QComboBox()
        self.cmb_code_holding.setFixedWidth(72)
        self.cmb_code_holding.addItem("未标记", userData="")
        self.cmb_code_holding.addItem("持有", userData="hold")
        self.cmb_code_holding.addItem("观察", userData="watch")
        self.cmb_code_holding.addItem("已清仓", userData="cleared")
        self.cmb_code_cycle = QComboBox()
        self.cmb_code_cycle.setFixedWidth(72)
        self.cmb_code_cycle.addItem("周期", userData="")
        self.cmb_code_cycle.addItem("短线", userData="short")
        self.cmb_code_cycle.addItem("波段", userData="swing")
        self.cmb_code_cycle.addItem("长期", userData="long")
        self.cmb_code_priority = QComboBox()
        self.cmb_code_priority.setFixedWidth(72)
        self.cmb_code_priority.addItem("优先级", userData="")
        self.cmb_code_priority.addItem("重点", userData="focus")
        self.cmb_code_priority.addItem("普通", userData="normal")
        self.cmb_code_priority.addItem("低优先", userData="low")

        g_code_tags = QGroupBox("标的标识")
        g_code_tags.setContentsMargins(3, 12, 3, 6)
        tag_lay = QHBoxLayout(g_code_tags)
        tag_lay.setContentsMargins(6, 6, 6, 6)
        tag_lay.setSpacing(6)
        tag_lay.addWidget(QLabel("状态"))
        tag_lay.addWidget(self.cmb_code_holding)
        tag_lay.addWidget(QLabel("周期"))
        tag_lay.addWidget(self.cmb_code_cycle)
        tag_lay.addWidget(QLabel("级别"))
        tag_lay.addWidget(self.cmb_code_priority)
        tag_lay.addStretch(1)

        lay_codes.addWidget(self.tree_codes, 1)
        lay_codes.addLayout(btn_col)
        code_settings.addWidget(g_codes, 1)
        code_settings.addWidget(g_code_tags)

        self.tabs.addTab(tab_0, "自选列表")

        # ---- 第二页 ----
        tab_1 = QWidget()
        data_settings = QVBoxLayout(tab_1)

        # 2.刷新间隔
        g_interval = QGroupBox("刷新间隔")
        g_interval.setContentsMargins(3,12,3,6)
        self.cmb_interval = QComboBox()
        self.cmb_interval.setFixedWidth(136)
        for s in [1,2,3,5,10,15,30,60]:
            self.cmb_interval.addItem(f"{s} 秒", userData=s)
        idx = self.cmb_interval.findData(self.win.refresh_seconds)
        self.cmb_interval.setCurrentIndex(idx if idx >= 0 else 1)
        v = QVBoxLayout(g_interval)
        v.setContentsMargins(6,6,6,6)
        v.addWidget(self.cmb_interval)
        data_settings.addWidget(g_interval)

        # 3.显示选项
        # 3.1复选框组
        g_flags = QGroupBox("显示指标")
        g_flags.setContentsMargins(3,12,3,6)
        gl_flags = QGridLayout(g_flags)
        self.cbs: list[QCheckBox] = []
        cb_texts = self.win.ALL_HEADERS

        g_flag_name = QGroupBox("名称")
        gl_flag_name = QGridLayout(g_flag_name)
        gl_flag_name.setHorizontalSpacing(6)
        gl_flag_name.setVerticalSpacing(6)
        # 代码、名称
        for i, h in enumerate(cb_texts[0:2]):
            cb = QCheckBox(h)
            cb.setChecked(self.win.header_is_visible(h))
            cb.stateChanged.connect(partial(self._on_cb_changed, h))
            self.cbs.append(cb)
            gl_flag_name.addWidget(cb, i, 0)
        self.cb_short_code = QCheckBox("仅显示数字")
        self.cb_short_code.setChecked(bool(self.win.short_code))
        self.cb_short_code.setEnabled(self.win.header_is_visible("代码"))
        gl_flag_name.addWidget(self.cb_short_code, 0, 1)
        self.cmb_namelength = QComboBox()
        self.cmb_namelength.setFixedWidth(80)
        for l in [0, 1, 2, 3, 4]:
            self.cmb_namelength.addItem(f"{l}个字" if l>0 else "完整", userData=l)
        idx_name = self.cmb_namelength.findData(self.win.name_length)
        self.cmb_namelength.setCurrentIndex(idx_name if idx_name>=0 else 1)
        self.cmb_namelength.setEnabled(self.win.header_is_visible("名称"))
        gl_flag_name.addWidget(self.cmb_namelength, 1, 1)
        gl_flags.addWidget(g_flag_name, 0, 0)

        g_flag_price = QGroupBox("价格")
        gl_flag_price = QGridLayout(g_flag_price)
        gl_flag_price.setHorizontalSpacing(6)
        gl_flag_price.setVerticalSpacing(6)
        # 现价、涨跌值、涨跌幅
        for i, h in enumerate(cb_texts[2:5]):
            cb = QCheckBox(h)
            cb.setChecked(self.win.header_is_visible(h))
            cb.stateChanged.connect(partial(self._on_cb_changed, h))
            self.cbs.append(cb)
            gl_flag_price.addWidget(cb, i, 0)
        gl_flags.addWidget(g_flag_price, 1, 0)

        g_flag_order = QGroupBox("盘口")
        gl_flag_order = QGridLayout(g_flag_order)
        gl_flag_order.setHorizontalSpacing(6)
        gl_flag_order.setVerticalSpacing(6)
        # 买一/卖一
        self.cb_b1s1 = QCheckBox("买一/卖一")
        self.cb_b1s1.setChecked(self.win.b1s1_visible)
        self.cb_b1s1.stateChanged.connect(self._on_b1s1_toggled)
        self.cbs.append(self.cb_b1s1)
        gl_flag_order.addWidget(self.cb_b1s1, 0, 0)
        
        # 委比
        cb_commi = QCheckBox("委比")
        cb_commi.setChecked(self.win.header_is_visible("委比"))
        cb_commi.stateChanged.connect(partial(self._on_cb_changed, "委比"))
        self.cbs.append(cb_commi)
        gl_flag_order.addWidget(cb_commi, 1, 0)
        
        # 买一/卖一显示模式：数量 / 价格 / 数量和价格
        self.cmb_b1s1_display = QComboBox()
        self.cmb_b1s1_display.setFixedWidth(100)
        self.cmb_b1s1_display.addItem("数量", userData="qty")
        self.cmb_b1s1_display.addItem("价格", userData="price")
        self.cmb_b1s1_display.addItem("数量和价格", userData="both")
        cur_mode = getattr(self.win, 'b1s1_display', 'qty')
        idx_mode = self.cmb_b1s1_display.findData(cur_mode)
        self.cmb_b1s1_display.setCurrentIndex(idx_mode if idx_mode>=0 else 0)
        self.cmb_b1s1_display.setEnabled(self.win.b1s1_visible)
        gl_flag_order.addWidget(self.cmb_b1s1_display, 0, 1)
        gl_flags.addWidget(g_flag_order, 0, 1)

        g_flag_deal = QGroupBox("成交")
        gl_flag_deal = QGridLayout(g_flag_deal)
        gl_flag_deal.setHorizontalSpacing(6)
        gl_flag_deal.setVerticalSpacing(6)
        for i in range(8,11):
            cb = QCheckBox(cb_texts[i])
            cb.setChecked(self.win.header_is_visible(cb_texts[i]))
            cb.stateChanged.connect(partial(self._on_cb_changed, cb_texts[i]))
            self.cbs.append(cb)
            gl_flag_deal.addWidget(cb, i-8, 0)
        gl_flags.addWidget(g_flag_deal, 1, 1)

        g_flag_other = QGroupBox("其他")
        gl_flag_other = QGridLayout(g_flag_other)
        gl_flag_other.setHorizontalSpacing(6)
        gl_flag_other.setVerticalSpacing(6)
        for i in range(11,12):
            cb = QCheckBox(cb_texts[i])
            cb.setChecked(self.win.header_is_visible(cb_texts[i]))
            cb.stateChanged.connect(partial(self._on_cb_changed, cb_texts[i]))
            self.cbs.append(cb)
            gl_flag_other.addWidget(cb, i-11, 0)
        self.chk_price_alert_badge_visible = QCheckBox("价格提醒标识")
        self.chk_price_alert_badge_visible.setChecked(bool(getattr(self.win, "price_alert_badge_visible", True)))
        gl_flag_other.addWidget(self.chk_price_alert_badge_visible, 1, 0)
        gl_flags.addWidget(g_flag_other, 2, 0)

        g_flag_strategy = QGroupBox("均线/策略")
        gl_flag_strategy = QGridLayout(g_flag_strategy)
        gl_flag_strategy.setHorizontalSpacing(6)
        gl_flag_strategy.setVerticalSpacing(6)
        for i, header in enumerate(cb_texts[12:]):
            cb = QCheckBox(header)
            cb.setChecked(self.win.header_is_visible(header))
            cb.stateChanged.connect(partial(self._on_cb_changed, header))
            self.cbs.append(cb)
            gl_flag_strategy.addWidget(cb, i // 2, i % 2)
        gl_flags.addWidget(g_flag_strategy, 2, 1)

        data_settings.addWidget(g_flags)

        self.tabs.addTab(tab_1, "显示数据")

        tab_source = QWidget()
        source_settings = QVBoxLayout(tab_source)
        source_cfg = getattr(self.win, "data_source", {}) or {}
        if not isinstance(source_cfg, dict):
            source_cfg = {}

        g_source = QGroupBox("数据源")
        g_source.setContentsMargins(3, 12, 3, 6)
        gl_source = QGridLayout(g_source)
        gl_source.setHorizontalSpacing(6)
        gl_source.setVerticalSpacing(6)

        self.cmb_data_source_mode = QComboBox()
        self.cmb_data_source_mode.addItem("内置演示源", userData="sina")
        self.cmb_data_source_mode.addItem("自定义 HTTP", userData="custom")
        source_mode = source_cfg.get("mode", "sina")
        idx_source = self.cmb_data_source_mode.findData(source_mode)
        self.cmb_data_source_mode.setCurrentIndex(idx_source if idx_source >= 0 else 0)

        self.edit_data_url = QLineEdit(str(source_cfg.get("url_template") or ""))
        self.edit_data_url.setPlaceholderText("https://example.com/quote?codes={codes}")
        headers = source_cfg.get("headers") if isinstance(source_cfg.get("headers"), dict) else {}
        self.edit_data_headers = QLineEdit(json.dumps(headers, ensure_ascii=False) if headers else "")
        self.edit_data_headers.setPlaceholderText('{"Authorization":"Bearer ..."}')

        gl_source.addWidget(QLabel("模式："), 0, 0)
        gl_source.addWidget(self.cmb_data_source_mode, 0, 1)
        gl_source.addWidget(QLabel("接口："), 1, 0)
        gl_source.addWidget(self.edit_data_url, 1, 1)
        gl_source.addWidget(QLabel("请求头："), 2, 0)
        gl_source.addWidget(self.edit_data_headers, 2, 1)
        source_settings.addWidget(g_source)
        source_settings.addStretch(1)
        self._sync_data_source_enabled()

        self.tab_source = tab_source

        # ---- 第三页：提醒 ----
        tab_alert = QWidget()
        alert_settings = QVBoxLayout(tab_alert)

        g_alert = QGroupBox("联动提醒")
        g_alert.setContentsMargins(3,12,3,6)
        lay_alert = QHBoxLayout(g_alert)
        lay_alert.setSpacing(6)

        left_alert = QVBoxLayout()
        self.list_alerts = QListWidget()
        self.list_alerts.setFixedWidth(185)
        self.list_alerts.setMinimumHeight(120)
        left_alert.addWidget(self.list_alerts)
        alert_btns = QHBoxLayout()
        self.btn_alert_add = QPushButton("添加")
        self.btn_alert_del = QPushButton("删除")
        self.btn_alert_add.setFixedWidth(82)
        self.btn_alert_del.setFixedWidth(82)
        alert_btns.addWidget(self.btn_alert_add)
        alert_btns.addWidget(self.btn_alert_del)
        left_alert.addLayout(alert_btns)
        lay_alert.addLayout(left_alert)

        form_alert = QGridLayout()
        form_alert.setHorizontalSpacing(6)
        form_alert.setVerticalSpacing(6)
        form_alert.setColumnMinimumWidth(0, 44)
        form_alert.setColumnMinimumWidth(1, 78)
        form_alert.setColumnMinimumWidth(2, 84)
        form_alert.setColumnMinimumWidth(3, 76)
        form_alert.setColumnMinimumWidth(4, 54)
        form_alert.setColumnStretch(4, 1)
        self.chk_alert_enabled = QCheckBox("启用")
        self.edit_alert_name = QLineEdit()
        self.cmb_alert_mode = QComboBox()
        self.cmb_alert_mode.addItem("触发时显示", userData="on_trigger")
        self.cmb_alert_mode.addItem("常显状态", userData="always")
        self.list_alert_targets = QListWidget()
        self.list_alert_targets.setMinimumHeight(112)
        self.btn_target_add = QPushButton("添加标的")
        self.btn_target_del = QPushButton("删除标的")
        self.btn_target_add.setFixedWidth(72)
        self.btn_target_del.setFixedWidth(72)
        self.edit_target_code = QLineEdit()
        self.cmb_target_op = QComboBox()
        self.cmb_target_op.addItem(">", userData=">")
        self.cmb_target_op.addItem(">=", userData=">=")
        self.spin_target_pct = QDoubleSpinBox()
        self.spin_target_pct.setRange(-20.0, 20.0)
        self.spin_target_pct.setDecimals(1)
        self.spin_target_pct.setSuffix("%")
        self.chk_target_volume = QCheckBox("放量")
        self.edit_alert_message = QLineEdit()
        self.edit_alert_message.setMinimumWidth(260)

        form_alert.addWidget(self.chk_alert_enabled, 0, 0)
        form_alert.addWidget(QLabel("名称："), 0, 1)
        form_alert.addWidget(self.edit_alert_name, 0, 2, 1, 3)
        form_alert.addWidget(QLabel("显示："), 1, 0)
        form_alert.addWidget(self.cmb_alert_mode, 1, 1, 1, 2)
        form_alert.addWidget(QLabel("标的："), 2, 0, Qt.AlignTop)
        target_editor = QHBoxLayout()
        target_editor.setSpacing(6)
        target_editor.addWidget(self.list_alert_targets)
        target_btns = QVBoxLayout()
        target_btns.setSpacing(4)
        target_btns.addWidget(self.btn_target_add)
        target_btns.addWidget(self.btn_target_del)
        target_btns.addStretch(1)
        target_editor.addLayout(target_btns)
        form_alert.addLayout(target_editor, 2, 1, 1, 4)
        form_alert.addWidget(QLabel("代码："), 3, 0)
        form_alert.addWidget(self.edit_target_code, 3, 1)
        form_alert.addWidget(self.cmb_target_op, 3, 2)
        form_alert.addWidget(self.spin_target_pct, 3, 3)
        form_alert.addWidget(self.chk_target_volume, 3, 4)
        form_alert.addWidget(QLabel("消息："), 4, 0)
        form_alert.addWidget(self.edit_alert_message, 4, 1, 1, 4)
        lay_alert.addLayout(form_alert, 1)
        alert_settings.addWidget(g_alert)

        g_price_alert = QGroupBox("价格提醒")
        g_price_alert.setContentsMargins(3,12,3,6)
        lay_price_alert = QVBoxLayout(g_price_alert)
        lay_price_alert.setSpacing(6)

        self.list_price_alerts = QListWidget()
        self.list_price_alerts.setVisible(False)
        price_btns = QHBoxLayout()
        self.btn_price_alert_add = QPushButton("保存")
        self.btn_price_alert_del = QPushButton("删除")
        self.btn_price_alert_add.setFixedWidth(64)
        self.btn_price_alert_del.setFixedWidth(64)
        price_btns.addStretch(1)
        price_btns.addWidget(self.btn_price_alert_add)
        price_btns.addWidget(self.btn_price_alert_del)

        form_price = QGridLayout()
        form_price.setHorizontalSpacing(6)
        form_price.setVerticalSpacing(6)
        self.lbl_price_alert_current = QLabel("当前标的：-")
        self.lbl_price_alert_current.setStyleSheet("color: #666666;")
        self.edit_price_alert_code = QLineEdit()
        self.edit_price_alert_code.setFixedWidth(92)
        self.edit_price_alert_code.setReadOnly(True)
        self.edit_price_alert_code.setVisible(False)
        self.cmb_price_alert_direction = QComboBox()
        self.cmb_price_alert_direction.setFixedWidth(96)
        self.cmb_price_alert_direction.addItem("高于/等于", userData="above")
        self.cmb_price_alert_direction.addItem("低于/等于", userData="below")
        self.spin_price_alert_price = QDoubleSpinBox()
        self.spin_price_alert_price.setRange(0.0, 99999.999)
        self.spin_price_alert_price.setDecimals(3)
        self.spin_price_alert_price.setFixedWidth(86)
        self.cmb_price_alert_direction.addItem("低于5日线", userData="below_ma5")
        self.cmb_price_alert_expire_days = QComboBox()
        self.cmb_price_alert_expire_days.setFixedWidth(76)
        for days in (1, 5, 30, 60):
            self.cmb_price_alert_expire_days.addItem(f"{days}日", userData=days)
        self.edit_price_alert_message = QLineEdit()
        self.edit_price_alert_message.setPlaceholderText("备注，可空")
        self.edit_price_alert_message.setMinimumWidth(120)

        form_price.addWidget(self.lbl_price_alert_current, 0, 0, 1, 4)
        form_price.addWidget(QLabel("条件："), 1, 0)
        form_price.addWidget(self.cmb_price_alert_direction, 1, 1)
        form_price.addWidget(self.spin_price_alert_price, 1, 2)
        form_price.addWidget(self.cmb_price_alert_expire_days, 1, 3)
        form_price.addWidget(QLabel("备注："), 2, 0)
        form_price.addWidget(self.edit_price_alert_message, 2, 1, 1, 3)
        form_price.setColumnStretch(3, 1)
        lay_price_alert.addLayout(form_price)
        lay_price_alert.addLayout(price_btns)
        code_settings.addWidget(g_price_alert)

        g_warning = QGroupBox("警醒标语")
        g_warning.setContentsMargins(3,12,3,6)
        lay_warning = QGridLayout(g_warning)
        self.chk_warning_visible = QCheckBox("显示")
        self.chk_warning_visible.setChecked(bool(getattr(self.win, "warning_visible", False)))
        self.edit_warning_text = QLineEdit(getattr(self.win, "warning_text", DEFAULT_WARNING_TEXT))
        lay_warning.addWidget(self.chk_warning_visible, 0, 0)
        lay_warning.addWidget(self.edit_warning_text, 0, 1)
        data_settings.addWidget(g_warning)

        g_market = QGroupBox("市场概览")
        g_market.setContentsMargins(3,12,3,6)
        lay_market = QGridLayout(g_market)
        self.chk_market_amount_visible = QCheckBox("显示沪深成交额估算")
        self.chk_market_amount_visible.setChecked(bool(getattr(self.win, "market_amount_visible", False)))
        lay_market.addWidget(self.chk_market_amount_visible, 0, 0)
        data_settings.addWidget(g_market)

        self._loading_alert_editor = False
        self._loading_target_editor = False
        self._loading_price_alert_editor = False
        self._load_alert_list()
        self._load_price_alert_list()
        if self.tree_codes.currentItem() is None and self.tree_codes.topLevelItemCount() > 0:
            group = self.tree_codes.topLevelItem(0)
            if group is not None and group.childCount() > 0:
                self.tree_codes.setCurrentItem(group.child(0))
        initial_code = self._current_code_from_tree()
        if initial_code:
            self._load_code_tag_editor()
            self._select_price_alert_for_code(initial_code)
        self._refresh_code_action_buttons()
        self.tab_alert_legacy = tab_alert

        # ---- 第四页：策略 ----
        tab_strategy = QWidget()
        strategy_main_layout = QVBoxLayout(tab_strategy)
        strategy_main_layout.setContentsMargins(4, 4, 4, 4)
        strategy_main_layout.setSpacing(4)

        self.strategy_subtabs = QTabWidget()
        self.strategy_subtabs.setStyleSheet("QTabWidget::pane { border: 1px solid #c0c0c0; background: #f0f0f0; }")
        strategy_main_layout.addWidget(self.strategy_subtabs)

        # ===== 子Tab 1: 持仓策略 =====
        tab_position_strategy = QScrollArea()
        tab_position_strategy.setWidgetResizable(True)
        tab_position_strategy.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_position_strategy_content = QWidget()
        position_strategy_layout = QVBoxLayout(tab_position_strategy_content)
        position_strategy_layout.setContentsMargins(4, 4, 4, 4)
        position_strategy_layout.setSpacing(4)

        # 持仓列表 GroupBox
        g_strategy_positions = QGroupBox("持仓列表")
        g_strategy_positions.setContentsMargins(6,14,6,8)
        lay_strategy_positions = QVBoxLayout(g_strategy_positions)
        lay_strategy_positions.setSpacing(8)

        strategy_left = QVBoxLayout()
        self.chk_strategy_enabled = QCheckBox("启用策略提醒")
        strategy_left.addWidget(self.chk_strategy_enabled)
        self.list_strategy_positions = QListWidget()
        self.list_strategy_positions.setMinimumSize(260, 100)
        strategy_left.addWidget(self.list_strategy_positions)
        strategy_btns = QHBoxLayout()
        strategy_btns.setSpacing(6)
        self.btn_strategy_add = QPushButton("添加")
        self.btn_strategy_del = QPushButton("删除")
        self.btn_strategy_save = QPushButton("保存持仓")
        self.btn_strategy_add.setFixedWidth(64)
        self.btn_strategy_del.setFixedWidth(64)
        self.btn_strategy_save.setFixedWidth(82)
        strategy_btns.addWidget(self.btn_strategy_add)
        strategy_btns.addWidget(self.btn_strategy_del)
        strategy_btns.addWidget(self.btn_strategy_save)
        strategy_btns.addStretch(1)
        strategy_left.addLayout(strategy_btns)
        lay_strategy_positions.addLayout(strategy_left)

        form_strategy_position = QGridLayout()
        form_strategy_position.setHorizontalSpacing(6)
        form_strategy_position.setVerticalSpacing(6)
        self.edit_strategy_code = QLineEdit()
        self.spin_strategy_cost = QDoubleSpinBox()
        self.spin_strategy_cost.setRange(0.0, 99999.999)
        self.spin_strategy_cost.setDecimals(3)
        self.spin_strategy_cost.setFixedWidth(92)
        self.edit_strategy_buy_date = QLineEdit()
        self.edit_strategy_buy_date.setPlaceholderText("YYYY-MM-DD")
        self.edit_strategy_note = QLineEdit()
        self.cmb_strategy_profile = QComboBox()
        self.cmb_strategy_profile.setMinimumWidth(120)
        self.btn_strategy_profile_clone = QPushButton("复制规则组")
        self.btn_strategy_profile_clone.setFixedWidth(90)
        self.edit_strategy_code.setFixedWidth(112)
        self.edit_strategy_buy_date.setFixedWidth(112)
        form_strategy_position.addWidget(QLabel("代码："), 0, 0)
        form_strategy_position.addWidget(self.edit_strategy_code, 0, 1)
        form_strategy_position.addWidget(QLabel("买入价："), 0, 2)
        form_strategy_position.addWidget(self.spin_strategy_cost, 0, 3)
        form_strategy_position.addWidget(QLabel("买入日期："), 1, 0)
        form_strategy_position.addWidget(self.edit_strategy_buy_date, 1, 1)
        form_strategy_position.addWidget(QLabel("备注："), 2, 0)
        form_strategy_position.addWidget(self.edit_strategy_note, 2, 1, 1, 3)
        form_strategy_position.addWidget(QLabel("策略模板："), 3, 0)
        form_strategy_position.addWidget(self.cmb_strategy_profile, 3, 1, 1, 2)
        form_strategy_position.addWidget(self.btn_strategy_profile_clone, 3, 3)
        self.strategy_position_detail = QWidget()
        self.strategy_position_detail.setLayout(form_strategy_position)
        form_strategy_position.setColumnStretch(1, 1)
        form_strategy_position.setColumnStretch(3, 1)
        lay_strategy_positions.addWidget(self.strategy_position_detail)
        position_strategy_layout.addWidget(g_strategy_positions)

        # 策略配置 GroupBox（重构：模板引用 + 参数覆盖）
        g_strategy_config = QGroupBox("策略配置")
        self.strategy_config_group = g_strategy_config
        self.strategy_rules_group = g_strategy_config
        g_strategy_config.setContentsMargins(6,14,6,8)
        g_strategy_config.setMinimumHeight(450)
        config_layout = QVBoxLayout(g_strategy_config)
        config_layout.setSpacing(8)

        # 操作按钮（放在参数列表上方，确保可见）
        params_action_layout = QHBoxLayout()
        params_action_layout.setSpacing(6)
        self.btn_strategy_template_reset = QPushButton("恢复默认")
        self.btn_strategy_template_reset.setFixedWidth(90)
        self.btn_strategy_params_edit = QPushButton("编辑参数")
        self.btn_strategy_params_edit.setFixedWidth(90)
        self.btn_strategy_params_save = QPushButton("保存参数")
        self.btn_strategy_params_save.setFixedWidth(90)
        self.btn_strategy_params_save.setVisible(False)
        params_action_layout.addWidget(self.btn_strategy_template_reset)
        params_action_layout.addWidget(self.btn_strategy_params_edit)
        params_action_layout.addWidget(self.btn_strategy_params_save)
        params_action_layout.addStretch(1)
        config_layout.addLayout(params_action_layout)

        # 参数覆盖状态列表（直接显示，无需模板引用文本）
        self.list_strategy_params = QListWidget()
        self.list_strategy_params.setFixedHeight(320)
        config_layout.addWidget(self.list_strategy_params)

        # 参数编辑区（默认隐藏，点击编辑后显示）
        self.strategy_params_editor = QWidget()
        params_editor_layout = QVBoxLayout(self.strategy_params_editor)
        params_editor_layout.setContentsMargins(0, 0, 0, 0)
        params_editor_layout.setSpacing(4)

        # 保留原有策略规则控件，但重新组织到分组中
        self.chk_strategy_loss = QCheckBox("浮亏达到")
        self.spin_strategy_loss = QDoubleSpinBox()
        self.spin_strategy_loss.setRange(0.0, 100.0)
        self.spin_strategy_loss.setDecimals(1)
        self.spin_strategy_loss.setSuffix("%")
        self.chk_strategy_stock_ma5 = QCheckBox("个股破5日线提醒卖出")
        self.chk_strategy_index_ma5 = QCheckBox("大盘破5日线提醒全仓卖出")
        self.chk_strategy_index_ma10 = QCheckBox("大盘破10日线提醒全仓卖出")
        self.chk_strategy_trailing = QCheckBox("阶梯移动止盈")
        self.spin_strategy_tier_profit = []
        self.spin_strategy_tier_lock = []
        self.strategy_tier_rows = []
        for _ in range(3):
            p = QDoubleSpinBox()
            p.setRange(0.0, 1000.0)
            p.setDecimals(1)
            p.setSuffix("%")
            p.setFixedWidth(72)
            l = QDoubleSpinBox()
            l.setRange(0.0, 1000.0)
            l.setDecimals(1)
            l.setSuffix("%")
            l.setFixedWidth(72)
            self.spin_strategy_tier_profit.append(p)
            self.spin_strategy_tier_lock.append(l)
        self.chk_strategy_skip_volume_drop = QCheckBox("放量大跌当日不提升止盈线")
        self.chk_strategy_reduce_half = QCheckBox("盈利达到")
        self.spin_strategy_reduce_half = QDoubleSpinBox()
        self.spin_strategy_reduce_half.setRange(0.0, 1000.0)
        self.spin_strategy_reduce_half.setDecimals(1)
        self.spin_strategy_reduce_half.setSuffix("%")
        self.chk_strategy_stale = QCheckBox("持仓满")
        self.spin_strategy_stale_days = QSpinBox()
        self.spin_strategy_stale_days.setRange(1, 3650)

        # 组织参数编辑控件到GroupBox中
        g_profit_rules = QGroupBox("止盈策略")
        profit_layout = QGridLayout(g_profit_rules)
        profit_layout.setHorizontalSpacing(6)
        profit_layout.setVerticalSpacing(4)
        profit_layout.addWidget(self.chk_strategy_loss, 0, 0)
        profit_layout.addWidget(self.spin_strategy_loss, 0, 1)
        profit_layout.addWidget(QLabel("提醒清仓"), 0, 2)
        profit_layout.addWidget(self.chk_strategy_reduce_half, 1, 0)
        profit_layout.addWidget(self.spin_strategy_reduce_half, 1, 1)
        profit_layout.addWidget(QLabel("提醒减半仓"), 1, 2)
        profit_layout.addWidget(self.chk_strategy_trailing, 2, 0, 1, 3)
        for i, (profit, lock) in enumerate(zip(self.spin_strategy_tier_profit, self.spin_strategy_tier_lock), start=3):
            tier_row = QWidget()
            tier_lay = QHBoxLayout(tier_row)
            tier_lay.setContentsMargins(0, 0, 0, 0)
            tier_lay.setSpacing(4)
            tier_label = QLabel(f"盈利{i - 2}档")
            tier_label.setFixedWidth(58)
            lock_label = QLabel("锁")
            lock_label.setFixedWidth(22)
            tier_lay.addWidget(tier_label)
            tier_lay.addWidget(profit)
            tier_lay.addWidget(lock_label)
            tier_lay.addWidget(lock)
            tier_lay.addStretch(1)
            self.strategy_tier_rows.append(tier_row)
            profit_layout.addWidget(tier_row, i, 0, 1, 4)

        g_loss_rules = QGroupBox("止损/风控策略")
        loss_layout = QVBoxLayout(g_loss_rules)
        loss_layout.setSpacing(4)
        loss_layout.addWidget(self.chk_strategy_stock_ma5)
        loss_layout.addWidget(self.chk_strategy_index_ma5)
        loss_layout.addWidget(self.chk_strategy_index_ma10)
        loss_layout.addWidget(self.chk_strategy_skip_volume_drop)

        g_position_rules = QGroupBox("持仓时间提醒")
        position_layout = QGridLayout(g_position_rules)
        position_layout.setHorizontalSpacing(6)
        position_layout.setVerticalSpacing(4)
        position_layout.addWidget(self.chk_strategy_stale, 0, 0)
        position_layout.addWidget(self.spin_strategy_stale_days, 0, 1)
        position_layout.addWidget(QLabel("天不上涨提醒卖出"), 0, 2, 1, 2)

        params_editor_layout.addWidget(g_profit_rules)
        params_editor_layout.addWidget(g_loss_rules)
        params_editor_layout.addWidget(g_position_rules)
        self.strategy_params_editor.setVisible(False)
        config_layout.addWidget(self.strategy_params_editor)

        self.lbl_strategy_scope = QLabel("请先选择持仓")
        self.lbl_strategy_scope.setStyleSheet("color: #666666;")
        position_strategy_layout.addWidget(self.lbl_strategy_scope)
        position_strategy_layout.addWidget(g_strategy_config)

        # 提醒方式 GroupBox（保留）
        g_strategy_notify = QGroupBox("提醒方式")
        self.strategy_notify_group = g_strategy_notify
        g_strategy_notify.setContentsMargins(6,14,6,8)
        notify = QGridLayout(g_strategy_notify)
        notify.setHorizontalSpacing(6)
        notify.setVerticalSpacing(6)
        self.chk_strategy_notify_desktop = QCheckBox("桌面弹窗")
        self.chk_strategy_notify_panel = QCheckBox("浮窗高亮")
        self.chk_strategy_notify_remote = QCheckBox("远程推送")
        self.cmb_strategy_remote_channel = QComboBox()
        self.cmb_strategy_remote_channel.addItem("企业微信机器人", userData="wecom")
        self.cmb_strategy_remote_channel.addItem("自定义Webhook", userData="custom")
        self.cmb_strategy_remote_channel.setFixedWidth(240)
        self.edit_strategy_webhook = QLineEdit()
        self.edit_strategy_webhook.setPlaceholderText("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...")
        self.edit_strategy_webhook.setMinimumWidth(220)
        self.edit_strategy_webhook.setFixedWidth(240)
        self.lbl_strategy_daily_summary_times = QLabel("交易日 09:00、18:00")
        self.btn_strategy_push_test = QPushButton("测试推送")
        self.btn_strategy_push_test.setFixedWidth(76)
        self.list_strategy_preview = QListWidget()
        self.list_strategy_preview.setFixedHeight(86)
        notify.addWidget(self.chk_strategy_notify_desktop, 0, 0)
        notify.addWidget(self.chk_strategy_notify_panel, 0, 1)
        notify.addWidget(self.chk_strategy_notify_remote, 0, 2)
        notify.addWidget(QLabel("推送类型："), 1, 0)
        notify.addWidget(self.cmb_strategy_remote_channel, 1, 1, 1, 3)
        notify.addWidget(QLabel("Webhook："), 2, 0)
        notify.addWidget(self.edit_strategy_webhook, 2, 1, 1, 3)
        notify.addWidget(QLabel("每日摘要："), 3, 0)
        notify.addWidget(self.lbl_strategy_daily_summary_times, 3, 1, 1, 3, Qt.AlignLeft)
        notify.addWidget(self.btn_strategy_push_test, 4, 1, Qt.AlignLeft)
        notify.addWidget(QLabel("提醒预览："), 5, 0, Qt.AlignTop)
        notify.addWidget(self.list_strategy_preview, 5, 1, 1, 3)
        position_strategy_layout.addWidget(g_strategy_notify)
        position_strategy_layout.addStretch(1)

        tab_position_strategy.setWidget(tab_position_strategy_content)
        self.strategy_subtabs.addTab(tab_position_strategy, "持仓策略")

        # ===== 子Tab 2: 策略库 =====
        tab_strategy_library = QWidget()
        strategy_library_layout = QVBoxLayout(tab_strategy_library)
        strategy_library_layout.setContentsMargins(4, 4, 4, 4)
        strategy_library_layout.setSpacing(4)

        # 模板列表 + 模板编辑
        library_splitter = QHBoxLayout()
        library_splitter.setSpacing(6)

        # 左侧：模板列表
        g_template_list = QGroupBox("模板列表")
        g_template_list.setContentsMargins(6,14,6,8)
        template_list_layout = QVBoxLayout(g_template_list)
        template_list_layout.setSpacing(4)
        self.btn_template_new = QPushButton("+ 新建模板")
        self.btn_template_new.setFixedWidth(90)
        self.btn_template_new.setVisible(False)
        template_list_layout.addWidget(self.btn_template_new)
        self.list_strategy_templates = QListWidget()
        self.list_strategy_templates.setFixedWidth(160)
        template_list_layout.addWidget(self.list_strategy_templates)
        library_splitter.addWidget(g_template_list)

        # 右侧：模板编辑
        g_template_edit = QGroupBox("模板编辑")
        g_template_edit.setContentsMargins(6,14,6,8)
        template_edit_layout = QVBoxLayout(g_template_edit)
        template_edit_layout.setSpacing(6)

        # 模板基本信息
        form_template_info = QGridLayout()
        form_template_info.setHorizontalSpacing(6)
        form_template_info.setVerticalSpacing(4)
        self.edit_template_name = QLineEdit()
        self.edit_template_name.setPlaceholderText("模板名称")
        self.edit_template_desc = QLineEdit()
        self.edit_template_desc.setPlaceholderText("模板描述")
        form_template_info.addWidget(QLabel("模板名称："), 0, 0)
        form_template_info.addWidget(self.edit_template_name, 0, 1)
        form_template_info.addWidget(QLabel("模板描述："), 1, 0)
        form_template_info.addWidget(self.edit_template_desc, 1, 1)
        template_edit_layout.addLayout(form_template_info)

        self.lbl_template_ref_count = QLabel("被引用：0 只股票")
        self.lbl_template_ref_count.setStyleSheet("color: #666666;")
        template_edit_layout.addWidget(self.lbl_template_ref_count)

        # 规则编辑区（放在滚动区域中）
        rules_scroll = QScrollArea()
        rules_scroll.setWidgetResizable(True)
        rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rules_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        rules_scroll_content = QWidget()
        template_rules_layout = QVBoxLayout(rules_scroll_content)
        template_rules_layout.setSpacing(4)
        template_rules_layout.setContentsMargins(0, 0, 0, 0)

        # 止盈策略
        g_template_profit = QGroupBox("止盈策略")
        template_profit_layout = QGridLayout(g_template_profit)
        template_profit_layout.setHorizontalSpacing(6)
        template_profit_layout.setVerticalSpacing(4)
        self.chk_template_loss = QCheckBox("浮亏达到")
        self.spin_template_loss = QDoubleSpinBox()
        self.spin_template_loss.setRange(0.0, 100.0)
        self.spin_template_loss.setDecimals(1)
        self.spin_template_loss.setSuffix("%")
        template_profit_layout.addWidget(self.chk_template_loss, 0, 0)
        template_profit_layout.addWidget(self.spin_template_loss, 0, 1)
        template_profit_layout.addWidget(QLabel("提醒清仓"), 0, 2)
        self.chk_template_reduce_half = QCheckBox("盈利达到")
        self.spin_template_reduce_half = QDoubleSpinBox()
        self.spin_template_reduce_half.setRange(0.0, 1000.0)
        self.spin_template_reduce_half.setDecimals(1)
        self.spin_template_reduce_half.setSuffix("%")
        template_profit_layout.addWidget(self.chk_template_reduce_half, 1, 0)
        template_profit_layout.addWidget(self.spin_template_reduce_half, 1, 1)
        template_profit_layout.addWidget(QLabel("提醒减半仓"), 1, 2)
        self.chk_template_trailing = QCheckBox("阶梯移动止盈")
        template_profit_layout.addWidget(self.chk_template_trailing, 2, 0, 1, 3)
        self.spin_template_tier_profit = []
        self.spin_template_tier_lock = []
        for i in range(3):
            p = QDoubleSpinBox()
            p.setRange(0.0, 1000.0)
            p.setDecimals(1)
            p.setSuffix("%")
            p.setFixedWidth(72)
            l = QDoubleSpinBox()
            l.setRange(0.0, 1000.0)
            l.setDecimals(1)
            l.setSuffix("%")
            l.setFixedWidth(72)
            self.spin_template_tier_profit.append(p)
            self.spin_template_tier_lock.append(l)
            tier_row = QWidget()
            tier_lay = QHBoxLayout(tier_row)
            tier_lay.setContentsMargins(0, 0, 0, 0)
            tier_lay.setSpacing(4)
            tier_label = QLabel(f"盈利{i + 1}档")
            tier_label.setFixedWidth(58)
            lock_label = QLabel("锁")
            lock_label.setFixedWidth(22)
            tier_lay.addWidget(tier_label)
            tier_lay.addWidget(p)
            tier_lay.addWidget(lock_label)
            tier_lay.addWidget(l)
            tier_lay.addStretch(1)
            template_profit_layout.addWidget(tier_row, 3 + i, 0, 1, 4)

        # 止损/风控策略
        g_template_loss = QGroupBox("止损/风控策略")
        template_loss_layout = QVBoxLayout(g_template_loss)
        template_loss_layout.setSpacing(4)
        self.chk_template_stock_ma5 = QCheckBox("个股破5日线提醒卖出")
        self.chk_template_index_ma5 = QCheckBox("大盘破5日线提醒全仓卖出")
        self.chk_template_index_ma10 = QCheckBox("大盘破10日线提醒全仓卖出")
        self.chk_template_skip_volume_drop = QCheckBox("放量大跌当日不提升止盈线")
        template_loss_layout.addWidget(self.chk_template_stock_ma5)
        template_loss_layout.addWidget(self.chk_template_index_ma5)
        template_loss_layout.addWidget(self.chk_template_index_ma10)
        template_loss_layout.addWidget(self.chk_template_skip_volume_drop)

        # 持仓时间提醒
        g_template_position = QGroupBox("持仓时间提醒")
        template_position_layout = QGridLayout(g_template_position)
        template_position_layout.setHorizontalSpacing(6)
        template_position_layout.setVerticalSpacing(4)
        self.chk_template_stale = QCheckBox("持仓满")
        self.spin_template_stale_days = QSpinBox()
        self.spin_template_stale_days.setRange(1, 3650)
        template_position_layout.addWidget(self.chk_template_stale, 0, 0)
        template_position_layout.addWidget(self.spin_template_stale_days, 0, 1)
        template_position_layout.addWidget(QLabel("天不上涨提醒卖出"), 0, 2, 1, 2)

        template_rules_layout.addWidget(g_template_profit)
        template_rules_layout.addWidget(g_template_loss)
        template_rules_layout.addWidget(g_template_position)
        self.g_template_profit = g_template_profit
        self.g_template_loss = g_template_loss
        self.g_template_position = g_template_position

        self.template_action_group = QGroupBox("动作规则")
        template_action_layout = QVBoxLayout(self.template_action_group)
        template_action_layout.setContentsMargins(6, 14, 6, 6)
        template_action_layout.setSpacing(4)
        self.lbl_template_action_hint = QLabel("该策略条件写死，只允许修改触发参数；新增策略需要通过代码加入。")
        self.lbl_template_action_hint.setStyleSheet("color: #666666;")
        self.spin_turtle_entry_days = QSpinBox()
        self.spin_turtle_entry_days.setRange(2, 250)
        self.spin_turtle_entry_days.setFixedWidth(72)
        self.spin_turtle_exit_days = QSpinBox()
        self.spin_turtle_exit_days.setRange(2, 250)
        self.spin_turtle_exit_days.setFixedWidth(72)
        self.spin_turtle_atr_stop = QDoubleSpinBox()
        self.spin_turtle_atr_stop.setRange(0.1, 20.0)
        self.spin_turtle_atr_stop.setDecimals(1)
        self.spin_turtle_atr_stop.setSuffix(" ATR")
        self.spin_turtle_atr_stop.setFixedWidth(82)
        self.spin_turtle_pyramid_atr = QDoubleSpinBox()
        self.spin_turtle_pyramid_atr.setRange(0.1, 20.0)
        self.spin_turtle_pyramid_atr.setDecimals(1)
        self.spin_turtle_pyramid_atr.setSuffix(" ATR")
        self.spin_turtle_pyramid_atr.setFixedWidth(82)
        self.spin_turtle_max_units = QSpinBox()
        self.spin_turtle_max_units.setRange(1, 20)
        self.spin_turtle_max_units.setFixedWidth(72)
        self.cmb_turtle_sizing = QComboBox()
        self.cmb_turtle_sizing.setFixedWidth(132)
        self.cmb_turtle_sizing.addItem("ATR风险计提", "atr_risk")
        self.cmb_turtle_sizing.addItem("固定百分比", "fixed_percent")
        self.cmb_turtle_sizing.addItem("仅动作提醒", "manual")

        self.g_template_turtle = QWidget()
        turtle_layout = QVBoxLayout(self.g_template_turtle)
        turtle_layout.setContentsMargins(0, 0, 0, 0)
        turtle_layout.setSpacing(4)

        self.g_turtle_entry = QGroupBox("入场策略")
        turtle_entry_layout = QGridLayout(self.g_turtle_entry)
        turtle_entry_layout.setHorizontalSpacing(6)
        turtle_entry_layout.setVerticalSpacing(4)
        turtle_entry_layout.addWidget(QLabel("突破："), 0, 0)
        turtle_entry_layout.addWidget(self.spin_turtle_entry_days, 0, 1)
        turtle_entry_layout.addWidget(QLabel("日新高提醒入场"), 0, 2)
        turtle_entry_layout.addWidget(QLabel("浮盈："), 1, 0)
        turtle_entry_layout.addWidget(self.spin_turtle_pyramid_atr, 1, 1)
        turtle_entry_layout.addWidget(QLabel("提醒加仓"), 1, 2)
        turtle_entry_layout.addWidget(QLabel("最大："), 2, 0)
        turtle_entry_layout.addWidget(self.spin_turtle_max_units, 2, 1)
        turtle_entry_layout.addWidget(QLabel("份"), 2, 2)
        turtle_entry_layout.addWidget(QLabel("计提："), 3, 0)
        turtle_entry_layout.addWidget(self.cmb_turtle_sizing, 3, 1, 1, 2)
        turtle_entry_layout.setColumnStretch(3, 1)

        self.g_turtle_stop = QGroupBox("止损策略")
        turtle_stop_layout = QGridLayout(self.g_turtle_stop)
        turtle_stop_layout.setHorizontalSpacing(6)
        turtle_stop_layout.setVerticalSpacing(4)
        turtle_stop_layout.addWidget(QLabel("止损："), 0, 0)
        turtle_stop_layout.addWidget(self.spin_turtle_atr_stop, 0, 1)
        turtle_stop_layout.addWidget(QLabel("提醒止损"), 0, 2)
        turtle_stop_layout.setColumnStretch(3, 1)

        self.g_turtle_exit = QGroupBox("止盈/退出策略")
        turtle_exit_layout = QGridLayout(self.g_turtle_exit)
        turtle_exit_layout.setHorizontalSpacing(6)
        turtle_exit_layout.setVerticalSpacing(4)
        turtle_exit_layout.addWidget(QLabel("离场："), 0, 0)
        turtle_exit_layout.addWidget(self.spin_turtle_exit_days, 0, 1)
        turtle_exit_layout.addWidget(QLabel("日低点提醒止盈/退出"), 0, 2)
        turtle_exit_layout.setColumnStretch(3, 1)

        turtle_layout.addWidget(self.g_turtle_entry)
        turtle_layout.addWidget(self.g_turtle_stop)
        turtle_layout.addWidget(self.g_turtle_exit)
        self.g_template_turtle.setVisible(False)
        template_rules_layout.addWidget(self.g_template_turtle)
        rules_scroll.setWidget(rules_scroll_content)
        self.template_rules_scroll = rules_scroll
        template_edit_layout.addWidget(rules_scroll)
        self.table_template_action_rules = QTableWidget(0, 7)
        self.table_template_action_rules.setHorizontalHeaderLabels(["启用", "指标", "比较", "参数", "计提单位", "动作", "附加"])
        self.table_template_action_rules.setMinimumHeight(240)
        self.table_template_action_rules.setMinimumWidth(680)
        self.table_template_action_rules.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table_template_action_rules.verticalHeader().setVisible(False)
        self.table_template_action_rules.setAlternatingRowColors(True)
        self.table_template_action_rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_template_action_rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table_template_action_rules.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table_template_action_rules.setColumnWidth(0, 54)
        self.table_template_action_rules.setColumnWidth(1, 110)
        self.table_template_action_rules.setColumnWidth(2, 110)
        self.table_template_action_rules.setColumnWidth(3, 88)
        self.table_template_action_rules.setColumnWidth(4, 110)
        self.table_template_action_rules.setColumnWidth(5, 140)
        self.table_template_action_rules.setColumnWidth(6, 80)
        self.list_template_action_rules = QListWidget()
        self.list_template_action_rules.setMinimumHeight(110)
        template_action_layout.addWidget(self.lbl_template_action_hint)
        self.table_template_action_rules.setVisible(False)
        template_action_layout.addWidget(self.table_template_action_rules)
        template_action_layout.addWidget(self.list_template_action_rules)
        self.template_action_group.setVisible(False)
        template_edit_layout.addWidget(self.template_action_group)

        # 操作按钮
        template_btn_layout = QHBoxLayout()
        template_btn_layout.setSpacing(6)
        self.btn_template_save = QPushButton("保存模板")
        self.btn_template_save.setFixedWidth(90)
        self.btn_template_copy = QPushButton("复制模板")
        self.btn_template_copy.setFixedWidth(90)
        self.btn_template_copy.setVisible(False)
        self.btn_template_delete = QPushButton("删除模板")
        self.btn_template_delete.setFixedWidth(90)
        self.btn_template_delete.setVisible(False)
        template_btn_layout.addWidget(self.btn_template_save)
        template_btn_layout.addWidget(self.btn_template_copy)
        template_btn_layout.addWidget(self.btn_template_delete)
        template_btn_layout.addStretch(1)
        template_edit_layout.addLayout(template_btn_layout)

        library_splitter.addWidget(g_template_edit)
        strategy_library_layout.addLayout(library_splitter)

        # 条件构建器
        g_condition_builder = QGroupBox("条件构建器（自定义规则）")
        g_condition_builder.setVisible(False)
        self.condition_builder_group = g_condition_builder
        g_condition_builder.setContentsMargins(6,14,6,8)
        condition_layout = QVBoxLayout(g_condition_builder)
        condition_layout.setSpacing(6)

        # 条件列表
        self.list_condition_rules = QListWidget()
        self.list_condition_rules.setFixedHeight(100)
        condition_layout.addWidget(self.list_condition_rules)

        # 条件编辑区
        condition_edit_layout = QHBoxLayout()
        condition_edit_layout.setSpacing(4)
        self.cmb_condition_indicator = QComboBox()
        self.cmb_condition_indicator.addItems(["收盘价", "5日均线", "10日均线", "成交量", "涨跌幅"])
        self.cmb_condition_operator = QComboBox()
        self.cmb_condition_operator.addItems(["大于", "小于", "大于等于", "小于等于", "突破", "跌破"])
        self.edit_condition_threshold = QLineEdit()
        self.edit_condition_threshold.setPlaceholderText("阈值")
        self.edit_condition_threshold.setFixedWidth(80)
        self.cmb_condition_action = QComboBox()
        self.cmb_condition_action.addItems(["提醒清仓", "提醒减半仓", "提醒卖出", "禁止新开仓"])
        self.btn_condition_add = QPushButton("+ 添加")
        self.btn_condition_add.setFixedWidth(70)
        condition_edit_layout.addWidget(self.cmb_condition_indicator)
        condition_edit_layout.addWidget(self.cmb_condition_operator)
        condition_edit_layout.addWidget(self.edit_condition_threshold)
        condition_edit_layout.addWidget(self.cmb_condition_action)
        condition_edit_layout.addWidget(self.btn_condition_add)
        condition_edit_layout.addStretch(1)
        condition_layout.addLayout(condition_edit_layout)

        # 逻辑连接
        logic_layout = QHBoxLayout()
        logic_layout.setSpacing(4)
        logic_layout.addWidget(QLabel("逻辑连接："))
        self.radio_logic_and = QRadioButton("且")
        self.radio_logic_or = QRadioButton("或")
        self.radio_logic_and.setChecked(True)
        logic_layout.addWidget(self.radio_logic_and)
        logic_layout.addWidget(self.radio_logic_or)
        logic_layout.addStretch(1)
        condition_layout.addLayout(logic_layout)

        lbl_condition_hint = QLabel("多条条件之间支持\"且/或\"逻辑组合，输出序列化为YAML")
        lbl_condition_hint.setStyleSheet("color: #666666;")
        condition_layout.addWidget(lbl_condition_hint)
        strategy_library_layout.addWidget(g_condition_builder)
        strategy_library_layout.addStretch(1)

        self.strategy_subtabs.addTab(tab_strategy_library, "策略库")

        # ===== 子Tab 3: 触发日志 =====
        tab_strategy_history = QWidget()
        strategy_history_layout = QVBoxLayout(tab_strategy_history)
        strategy_history_layout.setContentsMargins(6, 6, 6, 6)
        self.list_strategy_history = QListWidget()
        self.list_strategy_history.setMinimumHeight(260)
        strategy_history_layout.addWidget(self.list_strategy_history)
        self.strategy_subtabs.addTab(tab_strategy_history, "触发日志")

        self._loading_strategy_editor = False
        self._loading_code_tag_editor = False
        self._set_strategy_selection_visible(False)
        self._load_strategy_config()
        self._load_code_tag_editor()
        self.tabs.addTab(tab_strategy, "策略")

        # ---- 第四页 ----
        tab_2 = QWidget()
        appearance_settings = QVBoxLayout(tab_2)

        # 表格外观
        g_table = QGroupBox("表格外观")
        g_table.setContentsMargins(3,12,3,6)
        gl_table = QGridLayout(g_table)
        gl_table.setHorizontalSpacing(6)
        gl_table.setVerticalSpacing(6)
        # 复选框
        self.chk_table_header = QCheckBox("显示表头")
        self.chk_table_header.setChecked(self.win.header_visible)
        self.chk_table_grid = QCheckBox("显示网格")
        self.chk_table_grid.setChecked(self.win.grid_visible)

        gl_table.addWidget(self.chk_table_header,0,0)
        gl_table.addWidget(self.chk_table_grid,0,1)
        appearance_settings.addWidget(g_table)

        # 3.颜色/透明度
        g_color = QGroupBox("颜色与透明度")
        g_color.setContentsMargins(3,12,3,6)
        gl_color = QGridLayout(g_color)
        gl_color.setHorizontalSpacing(6)
        gl_color.setVerticalSpacing(6)
        # 3.1 复选框：默认颜色
        self.chk_default_color = QCheckBox("默认颜色")
        self.chk_default_color.setChecked(self.win.default_color)
        # 3.2 按钮：文字颜色
        self.btn_fg = QPushButton("文字颜色…")
        self.btn_fg.setFixedWidth(90)
        self.btn_fg.setEnabled(not self.win.default_color)
        # 3.3 按钮：背景颜色
        self.btn_bg = QPushButton("背景颜色…")
        self.btn_bg.setFixedWidth(90)
        # 3.4 滑块：背景不透明度
        self.slider_bg_alpha = QSlider(Qt.Horizontal)
        self.slider_bg_alpha.setRange(1, 100)
        self.slider_bg_alpha.setMinimumWidth(150)
        self.slider_bg_alpha.setValue(int(round(self.win.bg.alpha()/2.55)))
        self.lbl_bg_alpha = QLabel(f"{self.slider_bg_alpha.value()}%")
        # 3.5 滑块：整体不透明度
        self.slider_win_opacity = QSlider(Qt.Horizontal)
        self.slider_win_opacity.setRange(20, 100)
        self.slider_win_opacity.setMinimumWidth(150)
        self.slider_win_opacity.setValue(int(round(self.win.windowOpacity()*100)))
        self.lbl_win_opacity = QLabel(f"{self.slider_win_opacity.value()}%")

        gl_color.addWidget(self.chk_default_color,0,0,1,2)
        gl_color.addWidget(self.btn_fg,0,2,1,2)
        gl_color.addWidget(self.btn_bg,0,4,1,2)
        gl_color.addWidget(QLabel("背景不透明度："),1,0,1,2)
        gl_color.addWidget(self.slider_bg_alpha,1,2,1,3)
        gl_color.addWidget(self.lbl_bg_alpha,1,5,1,1)
        gl_color.addWidget(QLabel("整体不透明度："),2,0,1,2)
        gl_color.addWidget(self.slider_win_opacity,2,2,1,3)
        gl_color.addWidget(self.lbl_win_opacity,2,5,1,1)
        appearance_settings.addWidget(g_color)

        # 4.字体/行距
        g_font = QGroupBox("字体与行距")
        g_font.setContentsMargins(3,12,3,6)
        gl_font = QGridLayout(g_font)
        gl_font.setHorizontalSpacing(6)
        gl_font.setVerticalSpacing(6)
        # 4.1 选项：字体
        self.cmb_family = QComboBox()
        self.cmb_family.setFixedWidth(200)
        for fam in sorted(QFontDatabase.families()):
            self.cmb_family.addItem(fam)
        fi = self.cmb_family.findText(self.win.font.family())
        self.cmb_family.setCurrentIndex(fi if fi >= 0 else 0)
        # 4.2 滑块：字号
        self.slider_font = QSlider(Qt.Horizontal)
        self.slider_font.setRange(8, 15)
        self.slider_font.setMinimumWidth(150)
        self.slider_font.setValue(self.win.font.pointSize())
        self.lbl_font = QLabel(f"{self.slider_font.value()} pt")
        # 4.3 滑块：行间距
        self.slider_line = QSlider(Qt.Horizontal)
        self.slider_line.setRange(0, 20)
        self.slider_line.setMinimumWidth(150)
        self.slider_line.setValue(getattr(self.win,"line_extra_px",4))
        self.lbl_line = QLabel(f"+{self.slider_line.value()} px")

        gl_font.addWidget(QLabel("字体："),0,0,1,2)
        gl_font.addWidget(self.cmb_family,0,2,1,4)
        gl_font.addWidget(QLabel("字号："),1,0,1,2)
        gl_font.addWidget(self.slider_font,1,2,1,3)
        gl_font.addWidget(self.lbl_font,1,5,1,1)
        gl_font.addWidget(QLabel("行距："),2,0,1,2)
        gl_font.addWidget(self.slider_line,2,2,1,3)
        gl_font.addWidget(self.lbl_line,2,5,1,1)
        appearance_settings.addWidget(g_font)

        self.tabs.addTab(tab_2, "外观")

        # ---- 第五页 ----
        tab_3 = QWidget()
        other_settings = QVBoxLayout(tab_3)

        # 4.热键
        g_hotkey = QGroupBox("快捷键")
        g_hotkey.setContentsMargins(3,12,3,6)
        gl_hotkey = QGridLayout(g_hotkey)
        gl_hotkey.setHorizontalSpacing(6)
        gl_hotkey.setVerticalSpacing(6)
        gl_hotkey.addWidget(QLabel("隐藏/显示浮窗："),0,0,1,1)
        self.edit_hotkey = QKeySequenceEdit()
        self.edit_hotkey.setKeySequence(QKeySequence(self.win.hotkey))
        gl_hotkey.addWidget(self.edit_hotkey,0,1)
        # 开机启动复选框
        self.chk_start_on_boot = QCheckBox("开机启动")
        self.chk_start_on_boot.setChecked(bool(self.win.start_on_boot))
        other_settings.addWidget(self.chk_start_on_boot)
        other_settings.addWidget(g_hotkey)

        # 程序图标选择
        g_icon = QGroupBox("程序图标")
        g_icon.setContentsMargins(3,12,3,6)
        gl_icon = QHBoxLayout(g_icon)
        self.cmb_icon = QComboBox()
        icon_items = [
            ("默认", 'default'),
            ("系统：计算机", 'std:computer'),
            ("系统：网络", 'std:network'),
            ("系统：文件夹", 'std:folder'),
            ("系统：文件", 'std:file'),
            ("系统：回收站", 'std:trash'),
        ]
        for label, val in icon_items:
            self.cmb_icon.addItem(label, userData=val)
        self.btn_pick_icon = QPushButton("自定义图标…")
        self.btn_pick_icon.setFixedWidth(120)
        gl_icon.addWidget(self.cmb_icon)
        gl_icon.addWidget(self.btn_pick_icon)
        other_settings.addWidget(g_icon)

        self.tabs.addTab(tab_3, "常规")
        self.tabs.addTab(self.tab_source, "数据源")
        self._install_wheel_guards()

        # ---- 连接 ----
        # 连接：代码列表
        self.tree_codes.itemChanged.connect(self._on_codes_changed)
        self.tree_codes.currentItemChanged.connect(self._on_code_tree_selection_changed)
        self.btn_add.clicked.connect(self._add_code)
        self.btn_add_group.clicked.connect(self._add_group)
        self.btn_del.clicked.connect(self._del_code)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_dn.clicked.connect(self._move_down)
        self.btn_code_to_alert.clicked.connect(self._open_price_alert_for_current_code)
        self.btn_code_to_strategy.clicked.connect(self._open_strategy_for_current_code)
        self.cmb_code_holding.currentIndexChanged.connect(self._on_code_tag_changed)
        self.cmb_code_cycle.currentIndexChanged.connect(self._on_code_tag_changed)
        self.cmb_code_priority.currentIndexChanged.connect(self._on_code_tag_changed)
        self.list_alerts.currentRowChanged.connect(self._on_alert_selected)
        self.btn_alert_add.clicked.connect(self._add_alert_rule)
        self.btn_alert_del.clicked.connect(self._del_alert_rule)
        self.chk_alert_enabled.toggled.connect(self._on_alert_editor_changed)
        self.edit_alert_name.editingFinished.connect(self._on_alert_editor_changed)
        self.cmb_alert_mode.currentIndexChanged.connect(self._on_alert_editor_changed)
        self.list_alert_targets.currentRowChanged.connect(self._on_alert_target_selected)
        self.btn_target_add.clicked.connect(self._add_alert_target)
        self.btn_target_del.clicked.connect(self._del_alert_target)
        self.edit_target_code.editingFinished.connect(self._on_alert_target_editor_changed)
        self.cmb_target_op.currentIndexChanged.connect(self._on_alert_target_editor_changed)
        self.spin_target_pct.valueChanged.connect(self._on_alert_target_editor_changed)
        self.chk_target_volume.toggled.connect(self._on_alert_target_editor_changed)
        self.edit_alert_message.editingFinished.connect(self._on_alert_editor_changed)
        self.list_price_alerts.currentRowChanged.connect(self._on_price_alert_selected)
        self.btn_price_alert_add.clicked.connect(self._add_price_alert)
        self.btn_price_alert_del.clicked.connect(self._del_price_alert)
        self.edit_price_alert_code.editingFinished.connect(self._on_price_alert_editor_changed)
        self.cmb_price_alert_direction.currentIndexChanged.connect(self._on_price_alert_editor_changed)
        self.cmb_price_alert_expire_days.currentIndexChanged.connect(self._on_price_alert_editor_changed)
        self.spin_price_alert_price.valueChanged.connect(self._on_price_alert_editor_changed)
        self.edit_price_alert_message.editingFinished.connect(self._on_price_alert_editor_changed)
        self.chk_strategy_enabled.toggled.connect(self._on_strategy_config_changed)
        self.chk_strategy_notify_desktop.toggled.connect(self._on_strategy_config_changed)
        self.chk_strategy_notify_panel.toggled.connect(self._on_strategy_config_changed)
        self.chk_strategy_notify_remote.toggled.connect(self._on_strategy_config_changed)
        self.cmb_strategy_remote_channel.currentIndexChanged.connect(self._on_strategy_config_changed)
        self.edit_strategy_webhook.editingFinished.connect(self._on_strategy_config_changed)
        self.btn_strategy_push_test.clicked.connect(self._send_strategy_push_test)
        self.list_strategy_positions.currentRowChanged.connect(self._on_strategy_position_selected)
        self.cmb_strategy_profile.currentIndexChanged.connect(self._on_strategy_profile_selected)
        self.btn_strategy_profile_clone.clicked.connect(self._clone_strategy_profile)
        self.btn_strategy_add.clicked.connect(self._add_strategy_position)
        self.btn_strategy_del.clicked.connect(self._del_strategy_position)
        self.btn_strategy_save.clicked.connect(self._save_strategy_position)
        self.edit_strategy_code.editingFinished.connect(self._on_strategy_position_editor_changed)
        self.spin_strategy_cost.valueChanged.connect(self._on_strategy_position_editor_changed)
        self.edit_strategy_buy_date.editingFinished.connect(self._on_strategy_position_editor_changed)
        self.edit_strategy_note.editingFinished.connect(self._on_strategy_position_editor_changed)
        for checkbox in (
            self.chk_strategy_loss,
            self.chk_strategy_stock_ma5,
            self.chk_strategy_index_ma5,
            self.chk_strategy_index_ma10,
            self.chk_strategy_trailing,
            self.chk_strategy_skip_volume_drop,
            self.chk_strategy_reduce_half,
            self.chk_strategy_stale,
        ):
            checkbox.toggled.connect(self._on_strategy_config_changed)
        for spin in (
            self.spin_strategy_loss,
            self.spin_strategy_reduce_half,
            self.spin_strategy_stale_days,
            *self.spin_strategy_tier_profit,
            *self.spin_strategy_tier_lock,
        ):
            spin.valueChanged.connect(self._on_strategy_config_changed)
        self.btn_strategy_params_edit.clicked.connect(self._on_strategy_params_edit)
        self.btn_strategy_params_save.clicked.connect(self._on_strategy_params_save)
        self.btn_strategy_template_reset.clicked.connect(self._on_strategy_template_reset)
        self.list_strategy_templates.currentRowChanged.connect(self._on_strategy_template_selected)
        self.btn_template_new.clicked.connect(self._on_template_new)
        self.btn_template_save.clicked.connect(self._on_template_save)
        self.btn_template_copy.clicked.connect(self._on_template_copy)
        self.btn_template_delete.clicked.connect(self._on_template_delete)
        self.btn_condition_add.clicked.connect(self._on_condition_add)
        self.list_condition_rules.itemDoubleClicked.connect(self._on_condition_remove)
        # 模板规则控件信号连接
        for checkbox in (
            self.chk_template_loss,
            self.chk_template_stock_ma5,
            self.chk_template_index_ma5,
            self.chk_template_index_ma10,
            self.chk_template_trailing,
            self.chk_template_skip_volume_drop,
            self.chk_template_reduce_half,
            self.chk_template_stale,
        ):
            checkbox.toggled.connect(self._on_template_rules_changed)
        for spin in (
            self.spin_template_loss,
            self.spin_template_reduce_half,
            self.spin_template_stale_days,
            *self.spin_template_tier_profit,
            *self.spin_template_tier_lock,
        ):
            spin.valueChanged.connect(self._on_template_rules_changed)
        self.chk_warning_visible.toggled.connect(self._on_warning_changed)
        self.edit_warning_text.editingFinished.connect(self._on_warning_changed)
        self.chk_market_amount_visible.toggled.connect(self._on_market_amount_changed)
        self.chk_price_alert_badge_visible.toggled.connect(self._on_price_alert_badge_visible_changed)
        # 连接：其它设置
        self.cmb_interval.currentIndexChanged.connect(self._on_interval_changed)
        self.cmb_data_source_mode.currentIndexChanged.connect(self._on_data_source_changed)
        self.edit_data_url.editingFinished.connect(self._on_data_source_changed)
        self.edit_data_headers.editingFinished.connect(self._on_data_source_changed)
        self.cmb_namelength.currentIndexChanged.connect(self._on_name_length_changed)
        self.chk_default_color.toggled.connect(self._on_default_color_toggled)
        self.btn_fg.clicked.connect(self.pick_fg)
        self.btn_bg.clicked.connect(self.pick_bg)
        self.slider_bg_alpha.valueChanged.connect(self.apply_bg_alpha)
        self.slider_win_opacity.valueChanged.connect(self.apply_win_opacity)
        self.cmb_family.currentTextChanged.connect(self._on_family_changed)
        self.slider_font.valueChanged.connect(self.apply_font_size)
        self.slider_line.valueChanged.connect(self._on_line_changed)
        self.edit_hotkey.editingFinished.connect(self._on_hotkey_changed)
        self.chk_start_on_boot.toggled.connect(self._on_start_on_boot_toggled)
        self.chk_table_header.toggled.connect(self._on_header_toggled)
        self.chk_table_grid.toggled.connect(self._on_grid_toggled)
        # icon controls
        try:
            # set current index based on app config if available
            cur_choice = None
            if hasattr(self, 'app') and self.app is not None:
                cur_choice = getattr(self.app, '_app_icon_choice', None)
            if cur_choice is None:
                cur_choice = 'default'
            # find index
            idx = self.cmb_icon.findData(cur_choice)
            if idx < 0:
                if isinstance(cur_choice, str) and os.path.exists(cur_choice):
                    self.cmb_icon.addItem('自定义', userData=cur_choice)
                    idx = self.cmb_icon.count()-1
            self.cmb_icon.setCurrentIndex(idx if idx >= 0 else 0)
        except Exception:
            pass
        self.cmb_icon.currentIndexChanged.connect(self._on_icon_changed)
        self.btn_pick_icon.clicked.connect(self._pick_custom_icon)
        self.tabs.currentChanged.connect(self._apply_tab_size)
        self.cmb_b1s1_display.currentIndexChanged.connect(self._on_b1s1_display_changed)
        self.cb_short_code.stateChanged.connect(self._on_short_code_toggled)

    def _on_start_on_boot_toggled(self, checked: bool):
        try:
            self.win.set_start_on_boot(bool(checked))
            if hasattr(self, 'app') and self.app is not None:
                try:
                    self.app.set_start_on_boot(bool(checked))
                except Exception:
                    pass
        except Exception:
            pass

    # —— 分组自选列表 —— #
    def _pending_role(self):
        return Qt.UserRole + 2

    def _display_name_for_code(self, code: str):
        names = getattr(self.win, "code_names", {})
        if not isinstance(names, dict):
            names = {}
        name = str(names.get(code) or "").strip()
        return name[:2] if name else ""

    def _format_code_item_text(self, code: str):
        short_name = self._display_name_for_code(code)
        tags = self._code_tag_label(code)
        text = f"{code}  {short_name}" if short_name else code
        return f"{text}  [{tags}]" if tags else text

    def _code_tag_label(self, code: str):
        tags = getattr(self.win, "code_tags", {})
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

    def _code_from_item_text(self, text: str):
        text = str(text or "").strip()
        first = text.split()[0] if text.split() else text
        return normalize_code_or_none(first) or normalize_code_or_none(text)

    def _refresh_code_names(self, codes):
        lookup = getattr(self.win, "lookup_code_names", None)
        if not callable(lookup):
            return
        missing = []
        names = getattr(self.win, "code_names", {})
        if not isinstance(names, dict):
            names = {}
        for code in codes or []:
            if code and not str(names.get(code) or "").strip():
                missing.append(code)
        if not missing:
            return
        try:
            lookup(missing)
        except Exception:
            pass

    def _make_group_item(self, name: str):
        item = QTreeWidgetItem([str(name or "分组")])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setData(0, Qt.UserRole, "group")
        return item

    def _make_code_item(self, code: str, checked: bool, pending: bool = False):
        item = QTreeWidgetItem([code if pending else self._format_code_item_text(code)])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        item.setData(0, Qt.UserRole, "code")
        item.setData(0, Qt.UserRole + 1, None if pending else code)
        item.setData(0, self._pending_role(), bool(pending))
        return item

    def _load_code_tree(self):
        self.tree_codes.blockSignals(True)
        self.tree_codes.clear()
        checked = set(getattr(self.win, "checked_codes", []))
        groups = getattr(self.win, "groups", []) or [{"name": "默认", "codes": self.win.codes}]
        self._refresh_code_names(
            code
            for group in groups
            for code in group.get("codes", [])
        )
        for group in groups:
            group_item = self._make_group_item(group.get("name", "默认"))
            self.tree_codes.addTopLevelItem(group_item)
            for code in group.get("codes", []):
                group_item.addChild(self._make_code_item(code, code in checked))
            group_item.setExpanded(True)
        self.tree_codes.blockSignals(False)

    def _collect_groups_from_tree(self):
        groups = []
        checked_codes = []
        seen = set()
        self.tree_codes.blockSignals(True)
        try:
            for gi in range(self.tree_codes.topLevelItemCount()):
                group_item = self.tree_codes.topLevelItem(gi)
                name = group_item.text(0).strip() or "分组"
                if group_item.text(0) != name:
                    group_item.setText(0, name)
                codes = []
                ci = 0
                while ci < group_item.childCount():
                    child = group_item.child(ci)
                    norm = self._code_from_item_text(child.text(0))
                    if not norm:
                        if child.data(0, self._pending_role()):
                            ci += 1
                            continue
                        prev = child.data(0, Qt.UserRole + 1)
                        if prev:
                            child.setText(0, prev)
                            norm = prev
                        else:
                            group_item.removeChild(child)
                            continue
                    if norm in seen:
                        group_item.removeChild(child)
                        continue
                    seen.add(norm)
                    codes.append(norm)
                    self._refresh_code_names([norm])
                    display_text = self._format_code_item_text(norm)
                    if child.text(0) != display_text:
                        child.setText(0, display_text)
                    child.setData(0, Qt.UserRole + 1, norm)
                    child.setData(0, self._pending_role(), False)
                    if child.checkState(0) == Qt.Checked:
                        checked_codes.append(norm)
                    ci += 1
                if codes:
                    groups.append({"name": name, "codes": codes})
        finally:
            self.tree_codes.blockSignals(False)
        return groups, checked_codes

    def _on_codes_changed(self, _item):
        groups, checked_codes = self._collect_groups_from_tree()
        self.win.set_groups(groups)
        self.win.set_checked_codes(checked_codes or self.win.codes)

    def _current_group_item(self):
        item = self.tree_codes.currentItem()
        if item is None:
            if self.tree_codes.topLevelItemCount() == 0:
                self._add_group()
            return self.tree_codes.topLevelItem(0)
        return item if item.data(0, Qt.UserRole) == "group" else item.parent()

    def _current_code_from_tree(self):
        item = self.tree_codes.currentItem()
        if item is None or item.data(0, Qt.UserRole) != "code":
            return ""
        code = item.data(0, Qt.UserRole + 1) or self._code_from_item_text(item.text(0))
        return normalize_code_or_none(code) or ""

    def _set_combo_data(self, combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _on_code_tree_selection_changed(self, *_args):
        self._load_code_tag_editor()
        self._select_price_alert_for_code(self._current_code_from_tree())
        self._refresh_code_action_buttons()

    def _refresh_code_action_buttons(self):
        code = self._current_code_from_tree()
        has_code = bool(code)
        self.btn_code_to_alert.setEnabled(has_code)
        self.btn_code_to_strategy.setEnabled(has_code)
        self.btn_code_to_alert.setText("设提醒")
        self.btn_code_to_strategy.setText("设策略")

    def _load_code_tag_editor(self):
        code = self._current_code_from_tree()
        tags = getattr(self.win, "code_tags", {})
        if not isinstance(tags, dict):
            tags = {}
        item = tags.get(code) if code and isinstance(tags.get(code), dict) else {}
        self._loading_code_tag_editor = True
        try:
            self._set_combo_data(self.cmb_code_holding, item.get("holding", ""))
            self._set_combo_data(self.cmb_code_cycle, item.get("cycle", ""))
            self._set_combo_data(self.cmb_code_priority, item.get("priority", ""))
            enabled = bool(code)
            self.cmb_code_holding.setEnabled(enabled)
            self.cmb_code_cycle.setEnabled(enabled)
            self.cmb_code_priority.setEnabled(enabled)
        finally:
            self._loading_code_tag_editor = False

    def _on_code_tag_changed(self, *_args):
        if getattr(self, "_loading_code_tag_editor", False):
            return
        code = self._current_code_from_tree()
        if not code:
            return
        code_tags = dict(getattr(self.win, "code_tags", {}) if isinstance(getattr(self.win, "code_tags", {}), dict) else {})
        tags = {
            "holding": self.cmb_code_holding.currentData() or "",
            "cycle": self.cmb_code_cycle.currentData() or "",
            "priority": self.cmb_code_priority.currentData() or "",
        }
        if any(tags.values()):
            code_tags[code] = tags
        else:
            code_tags.pop(code, None)
        setter = getattr(self.win, "set_code_tags", None)
        if callable(setter):
            setter(code_tags)
        else:
            self.win.code_tags = code_tags
        item = self.tree_codes.currentItem()
        if item is not None and item.data(0, Qt.UserRole) == "code":
            item.setText(0, self._format_code_item_text(code))

    def _open_price_alert_for_current_code(self):
        code = self._current_code_from_tree()
        if not code:
            return
        alerts = list(getattr(self, "_price_alerts", normalize_price_alerts(getattr(self.win, "price_alerts", []))))
        target_row = -1
        for row, alert in enumerate(alerts):
            if normalize_price_alert(alert).get("code") == code:
                target_row = row
                break
        if target_row < 0:
            alert = default_price_alert()
            alert["code"] = code
            alerts.append(alert)
            self.win.set_price_alerts(alerts)
            target_row = len(alerts) - 1
        self._load_price_alert_list(target_row)
        self.edit_price_alert_code.setFocus(Qt.OtherFocusReason)
        self.edit_price_alert_code.selectAll()

    def _select_price_alert_for_code(self, code):
        if not code or not hasattr(self, "list_price_alerts"):
            return
        code_text = self._format_code_item_text(code)
        if hasattr(self, "lbl_price_alert_current"):
            self.lbl_price_alert_current.setText(code_text)
        alerts = list(getattr(self, "_price_alerts", normalize_price_alerts(getattr(self.win, "price_alerts", []))))
        for row, alert in enumerate(alerts):
            if normalize_price_alert(alert).get("code") == code:
                self.list_price_alerts.setCurrentRow(row)
                return
        self.list_price_alerts.setCurrentRow(-1)
        self._loading_price_alert_editor = True
        try:
            alert = default_price_alert()
            alert["code"] = code
            self.edit_price_alert_code.setText(alert.get("code", "sh000001"))
            idx = self.cmb_price_alert_direction.findData(alert.get("direction", "above"))
            self.cmb_price_alert_direction.setCurrentIndex(idx if idx >= 0 else 0)
            expire_idx = self.cmb_price_alert_expire_days.findData(int(alert.get("expire_days", 30)))
            self.cmb_price_alert_expire_days.setCurrentIndex(expire_idx if expire_idx >= 0 else self.cmb_price_alert_expire_days.findData(30))
            self.spin_price_alert_price.setValue(float(alert.get("price", 0.0)))
            self.edit_price_alert_message.setText(alert.get("message", ""))
            self._sync_price_alert_direction_controls()
        finally:
            self._loading_price_alert_editor = False

    def _open_strategy_for_current_code(self):
        code = self._current_code_from_tree()
        if not code:
            return
        config = normalize_strategy_alert_config(getattr(self, "_strategy_config", getattr(self.win, "strategy_alert_config", {})))
        target_row = -1
        for row, position in enumerate(config.get("positions", [])):
            normalized_position = normalize_strategy_position(position) or {}
            if normalized_position.get("code") == code:
                target_row = row
                break
        if target_row < 0:
            config["positions"].append({
                "code": code,
                "strategy_id": "default",
                "cost_price": 0.0,
                "buy_date": date.today().strftime("%Y-%m-%d"),
                "note": "",
                "rules": {},
            })
            self.win.set_strategy_alert_config(config)
            self._strategy_config = config
            target_row = len(config["positions"]) - 1
        self.tabs.setCurrentIndex(2)
        if hasattr(self, "strategy_subtabs"):
            self.strategy_subtabs.setCurrentIndex(0)
        self._load_strategy_config(target_row)
        self.edit_strategy_code.setFocus(Qt.OtherFocusReason)
        self.edit_strategy_code.selectAll()

    def _strategy_allowed_codes(self):
        return set(normalize_codes(getattr(self.win, "codes", [])))

    def _filter_strategy_config_to_self_selected(self, config):
        config = normalize_strategy_alert_config(config)
        allowed = self._strategy_allowed_codes()
        if not allowed:
            config["positions"] = []
            return config
        config["positions"] = [
            position for position in config.get("positions", [])
            if normalize_code_or_none(position.get("code")) in allowed
        ]
        return config

    def _add_group(self):
        item = self._make_group_item("新分组")
        self.tree_codes.addTopLevelItem(item)
        self.tree_codes.setCurrentItem(item)
        self.tree_codes.editItem(item, 0)

    def _add_code(self):
        group_item = self._current_group_item()
        if group_item is None:
            return
        it = self._make_code_item("输入代码", False, pending=True)
        self.tree_codes.blockSignals(True)
        try:
            group_item.addChild(it)
            group_item.setExpanded(True)
            self.tree_codes.setCurrentItem(it)
        finally:
            self.tree_codes.blockSignals(False)
        self.tree_codes.editItem(it, 0)

    def _del_code(self):
        item = self.tree_codes.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            idx = self.tree_codes.indexOfTopLevelItem(item)
            self.tree_codes.takeTopLevelItem(idx)
        else:
            parent.removeChild(item)
        self._on_codes_changed(None)

    def _move_up(self):
        item = self.tree_codes.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            row = self.tree_codes.indexOfTopLevelItem(item)
            if row > 0:
                item = self.tree_codes.takeTopLevelItem(row)
                self.tree_codes.insertTopLevelItem(row - 1, item)
                self.tree_codes.setCurrentItem(item)
        else:
            row = parent.indexOfChild(item)
            if row > 0:
                item = parent.takeChild(row)
                parent.insertChild(row - 1, item)
                self.tree_codes.setCurrentItem(item)
        self._on_codes_changed(None)

    def _move_down(self):
        item = self.tree_codes.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            row = self.tree_codes.indexOfTopLevelItem(item)
            if 0 <= row < self.tree_codes.topLevelItemCount() - 1:
                item = self.tree_codes.takeTopLevelItem(row)
                self.tree_codes.insertTopLevelItem(row + 1, item)
                self.tree_codes.setCurrentItem(item)
        else:
            row = parent.indexOfChild(item)
            if 0 <= row < parent.childCount() - 1:
                item = parent.takeChild(row)
                parent.insertChild(row + 1, item)
                self.tree_codes.setCurrentItem(item)
        self._on_codes_changed(None)

    # —— 联动提醒 —— #
    def _load_alert_list(self, current_row=0):
        self.list_alerts.blockSignals(True)
        self.list_alerts.clear()
        self._alert_rules = normalize_alert_rules(getattr(self.win, "alert_rules", []))
        for rule in self._alert_rules:
            self.list_alerts.addItem(QListWidgetItem(rule.get("name", "联动提醒")))
        self.list_alerts.blockSignals(False)
        if self.list_alerts.count() > 0:
            self.list_alerts.setCurrentRow(max(0, min(current_row, self.list_alerts.count() - 1)))
            self._on_alert_selected(self.list_alerts.currentRow())

    def _current_alert_row(self):
        row = self.list_alerts.currentRow()
        return row if 0 <= row < len(getattr(self, "_alert_rules", [])) else -1

    def _on_alert_selected(self, row: int):
        if row < 0 or row >= len(getattr(self, "_alert_rules", [])):
            return
        rule = normalize_alert_rule(self._alert_rules[row])
        self._loading_alert_editor = True
        try:
            self.chk_alert_enabled.setChecked(bool(rule.get("enabled")))
            self.edit_alert_name.setText(rule.get("name", "联动提醒"))
            idx = self.cmb_alert_mode.findData(rule.get("display_mode", "on_trigger"))
            self.cmb_alert_mode.setCurrentIndex(idx if idx >= 0 else 0)
            self.edit_alert_message.setText(rule.get("message", ""))
            self._load_target_list(rule.get("targets", []))
        finally:
            self._loading_alert_editor = False

    def _format_target(self, target):
        op = target.get("op", ">=")
        vol = "+放量" if target.get("volume") else ""
        return f"{target.get('code', '')} {op} {float(target.get('pct', 0.0)):.1f}%{vol}"

    def _load_target_list(self, targets, current_row=0):
        self._loading_target_editor = True
        self.list_alert_targets.blockSignals(True)
        self.list_alert_targets.clear()
        for target in targets or []:
            item = QListWidgetItem(self._format_target(target))
            item.setData(Qt.UserRole, dict(target))
            self.list_alert_targets.addItem(item)
        self.list_alert_targets.blockSignals(False)
        try:
            if self.list_alert_targets.count() > 0:
                self.list_alert_targets.setCurrentRow(max(0, min(current_row, self.list_alert_targets.count() - 1)))
                self._on_alert_target_selected(self.list_alert_targets.currentRow())
        finally:
            self._loading_target_editor = False

    def _current_target_row(self):
        row = self.list_alert_targets.currentRow()
        return row if 0 <= row < self.list_alert_targets.count() else -1

    def _targets_from_list(self):
        targets = []
        for i in range(self.list_alert_targets.count()):
            data = self.list_alert_targets.item(i).data(Qt.UserRole)
            target = normalize_alert_target(data)
            if target:
                targets.append(target)
        return targets

    def _collect_alert_from_editor(self):
        row = self._current_alert_row()
        existing = self._alert_rules[row] if row >= 0 else {}
        return normalize_alert_rule({
            "enabled": self.chk_alert_enabled.isChecked(),
            "name": self.edit_alert_name.text(),
            "display_mode": self.cmb_alert_mode.currentData(),
            "targets": self._targets_from_list() or existing.get("targets", []),
            "message": self.edit_alert_message.text(),
        })

    def _on_alert_editor_changed(self, *_args):
        if getattr(self, "_loading_alert_editor", False):
            return
        row = self._current_alert_row()
        if row < 0:
            return
        rule = self._collect_alert_from_editor()
        self._alert_rules[row] = rule
        item = self.list_alerts.item(row)
        if item:
            item.setText(rule.get("name", "联动提醒"))
        self.win.set_alert_rules(self._alert_rules)

    def _on_alert_target_selected(self, row: int):
        if row < 0 or row >= self.list_alert_targets.count():
            return
        target = normalize_alert_target(self.list_alert_targets.item(row).data(Qt.UserRole))
        if not target:
            return
        self._loading_target_editor = True
        try:
            self.edit_target_code.setText(target.get("code", ""))
            idx = self.cmb_target_op.findData(target.get("op", ">="))
            self.cmb_target_op.setCurrentIndex(idx if idx >= 0 else 1)
            self.spin_target_pct.setValue(float(target.get("pct", 0.0)))
            self.chk_target_volume.setChecked(bool(target.get("volume", False)))
        finally:
            self._loading_target_editor = False

    def _on_alert_target_editor_changed(self, *_args):
        if getattr(self, "_loading_alert_editor", False) or getattr(self, "_loading_target_editor", False):
            return
        row = self._current_target_row()
        if row < 0:
            return
        target = normalize_alert_target({
            "code": self.edit_target_code.text(),
            "op": self.cmb_target_op.currentData(),
            "pct": self.spin_target_pct.value(),
            "volume": self.chk_target_volume.isChecked(),
        })
        if not target:
            self._on_alert_target_selected(row)
            return
        item = self.list_alert_targets.item(row)
        item.setData(Qt.UserRole, target)
        item.setText(self._format_target(target))
        self._on_alert_editor_changed()

    def _new_target_code(self):
        existing = {target.get("code") for target in self._targets_from_list()}
        for code in ("sh000001", "sh512000", "sh515880", "sh513100"):
            if code not in existing:
                return code
        return "sh000001"

    def _add_alert_target(self):
        target = {"code": self._new_target_code(), "op": ">=", "pct": 0.0, "volume": False}
        item = QListWidgetItem(self._format_target(target))
        item.setData(Qt.UserRole, target)
        self.list_alert_targets.addItem(item)
        self.list_alert_targets.setCurrentItem(item)
        self._on_alert_editor_changed()

    def _del_alert_target(self):
        row = self._current_target_row()
        if row < 0:
            return
        self.list_alert_targets.takeItem(row)
        self._on_alert_editor_changed()
        if self.list_alert_targets.count() > 0:
            self.list_alert_targets.setCurrentRow(max(0, min(row, self.list_alert_targets.count() - 1)))

    def _add_alert_rule(self):
        rules = list(getattr(self, "_alert_rules", normalize_alert_rules([])))
        rule = default_alert_rule()
        rule["enabled"] = True
        rules.append(rule)
        self.win.set_alert_rules(rules)
        self._load_alert_list(len(rules) - 1)

    def _del_alert_rule(self):
        row = self._current_alert_row()
        if row < 0:
            return
        rules = list(getattr(self, "_alert_rules", []))
        if 0 <= row < len(rules):
            rules.pop(row)
        self.win.set_alert_rules(rules)
        self._load_alert_list(max(0, row - 1))

    # —— 价格提醒 —— #
    def _format_price_alert(self, alert):
        code = alert.get("code", "")
        if alert.get("direction") == "below_ma5":
            direction = "低于5日线"
            price_text = ""
        else:
            direction = "高于" if alert.get("direction") == "above" else "低于"
            price_text = f" {float(alert.get('price', 0.0)):.3f}"
        suffix = "" if alert.get("enabled", True) else "（停用）"
        return f"{self._format_code_item_text(code)} {direction}{price_text} {int(alert.get('expire_days', 30))}日{suffix}"

    def _load_price_alert_list(self, current_row=0):
        self.list_price_alerts.blockSignals(True)
        self.list_price_alerts.clear()
        self._price_alerts = normalize_price_alerts(getattr(self.win, "price_alerts", []))
        self._refresh_code_names(alert.get("code") for alert in self._price_alerts)
        for alert in self._price_alerts:
            self.list_price_alerts.addItem(QListWidgetItem(self._format_price_alert(alert)))
        self.list_price_alerts.blockSignals(False)
        if self.list_price_alerts.count() > 0:
            self.list_price_alerts.setCurrentRow(max(0, min(current_row, self.list_price_alerts.count() - 1)))
            self._on_price_alert_selected(self.list_price_alerts.currentRow())

    def _current_price_alert_row(self):
        row = self.list_price_alerts.currentRow()
        return row if 0 <= row < len(getattr(self, "_price_alerts", [])) else -1

    def _on_price_alert_selected(self, row: int):
        if row < 0 or row >= len(getattr(self, "_price_alerts", [])):
            return
        alert = normalize_price_alert(self._price_alerts[row])
        self._loading_price_alert_editor = True
        try:
            self.edit_price_alert_code.setText(alert.get("code", "sh000001"))
            idx = self.cmb_price_alert_direction.findData(alert.get("direction", "above"))
            self.cmb_price_alert_direction.setCurrentIndex(idx if idx >= 0 else 0)
            expire_idx = self.cmb_price_alert_expire_days.findData(int(alert.get("expire_days", 30)))
            self.cmb_price_alert_expire_days.setCurrentIndex(expire_idx if expire_idx >= 0 else self.cmb_price_alert_expire_days.findData(30))
            self.spin_price_alert_price.setValue(float(alert.get("price", 0.0)))
            self.edit_price_alert_message.setText(alert.get("message", ""))
            self._sync_price_alert_direction_controls()
        finally:
            self._loading_price_alert_editor = False

    def _collect_price_alert_from_editor(self):
        row = self._current_price_alert_row()
        existing = self._price_alerts[row] if row >= 0 else {}
        created_date = str((existing or {}).get("created_date") or "").strip() or date.today().strftime("%Y-%m-%d")
        return normalize_price_alert({
            "enabled": True,
            "code": self._current_code_from_tree() or self.edit_price_alert_code.text(),
            "direction": self.cmb_price_alert_direction.currentData(),
            "price": self.spin_price_alert_price.value(),
            "message": self.edit_price_alert_message.text(),
            "created_date": created_date,
            "expire_days": self.cmb_price_alert_expire_days.currentData() or 30,
        })

    def _sync_price_alert_direction_controls(self):
        is_ma_alert = self.cmb_price_alert_direction.currentData() == "below_ma5"
        self.spin_price_alert_price.setEnabled(not is_ma_alert)

    def _on_price_alert_editor_changed(self, *_args):
        if getattr(self, "_loading_price_alert_editor", False):
            return
        self._sync_price_alert_direction_controls()
        row = self._current_price_alert_row()
        if row < 0:
            return
        alert = self._collect_price_alert_from_editor()
        self._price_alerts[row] = alert
        item = self.list_price_alerts.item(row)
        if item:
            item.setText(self._format_price_alert(alert))
        self.win.set_price_alerts(self._price_alerts)

    def _add_price_alert(self):
        current_code = self._current_code_from_tree()
        if not current_code:
            return
        alerts = list(getattr(self, "_price_alerts", normalize_price_alerts(getattr(self.win, "price_alerts", []))))
        alert = self._collect_price_alert_from_editor()
        alert["code"] = current_code
        target_row = -1
        for row, existing in enumerate(alerts):
            if normalize_price_alert(existing).get("code") == current_code:
                target_row = row
                break
        if target_row >= 0:
            alerts[target_row] = alert
        else:
            alerts.append(alert)
            target_row = len(alerts) - 1
        self.win.set_price_alerts(alerts)
        self._load_price_alert_list(target_row)
        self._select_price_alert_for_code(current_code)

    def _del_price_alert(self):
        current_code = self._current_code_from_tree()
        if not current_code:
            return
        alerts = list(getattr(self, "_price_alerts", []))
        alerts = [alert for alert in alerts if normalize_price_alert(alert).get("code") != current_code]
        self.win.set_price_alerts(alerts)
        self._load_price_alert_list()
        self._select_price_alert_for_code(current_code)

    # —— 策略提醒 —— #
    def _format_strategy_position(self, position):
        code = position.get("code", "")
        cost = float(position.get("cost_price", 0.0))
        date = position.get("buy_date", "")
        date_part = f" {date}" if date else ""
        return f"{self._format_code_item_text(code)} 成本 {cost:.3f}{date_part}"

    def _load_strategy_config(self, current_row=None):
        original_config = normalize_strategy_alert_config(getattr(self.win, "strategy_alert_config", {}))
        self._strategy_config = self._filter_strategy_config_to_self_selected(original_config)
        if self._strategy_config.get("positions") != original_config.get("positions"):
            self.win.set_strategy_alert_config(self._strategy_config)
        rules = self._strategy_config["rules"]
        notifications = self._strategy_config["notifications"]
        self._loading_strategy_editor = True
        try:
            self.chk_strategy_enabled.setChecked(bool(self._strategy_config.get("enabled")))
            self.chk_strategy_notify_desktop.setChecked(bool(notifications.get("desktop_popup")))
            self.chk_strategy_notify_panel.setChecked(bool(notifications.get("panel_highlight")))
            self.chk_strategy_notify_remote.setChecked(bool(notifications.get("remote_push")))
            channel_idx = self.cmb_strategy_remote_channel.findData(notifications.get("remote_channel", "wecom"))
            self.cmb_strategy_remote_channel.setCurrentIndex(channel_idx if channel_idx >= 0 else 0)
            self.edit_strategy_webhook.setText(notifications.get("webhook_url", ""))
            self.chk_strategy_loss.setChecked(bool(rules.get("max_loss_enabled")))
            self.spin_strategy_loss.setValue(float(rules.get("max_loss_pct", 5.0)))
            self.chk_strategy_stock_ma5.setChecked(bool(rules.get("stock_ma5_break_enabled")))
            self.chk_strategy_index_ma5.setChecked(bool(rules.get("index_ma5_break_enabled")))
            self.chk_strategy_index_ma10.setChecked(bool(rules.get("index_ma10_break_enabled")))
            self.chk_strategy_trailing.setChecked(bool(rules.get("trailing_profit_enabled")))
            tiers = rules.get("trailing_tiers", [])
            for i, (profit, lock) in enumerate(zip(self.spin_strategy_tier_profit, self.spin_strategy_tier_lock)):
                tier = tiers[i] if i < len(tiers) else {}
                profit.setValue(float(tier.get("profit_pct", 0.0)))
                lock.setValue(float(tier.get("lock_pct", 0.0)))
            self.chk_strategy_skip_volume_drop.setChecked(bool(rules.get("skip_raise_on_volume_drop")))
            self.chk_strategy_reduce_half.setChecked(bool(rules.get("reduce_half_enabled")))
            self.spin_strategy_reduce_half.setValue(float(rules.get("reduce_half_profit_pct", 45.0)))
            self.chk_strategy_stale.setChecked(bool(rules.get("stale_position_enabled")))
            self.spin_strategy_stale_days.setValue(int(rules.get("stale_position_days", 12)))

            self.list_strategy_positions.blockSignals(True)
            self.list_strategy_positions.clear()
            self._refresh_code_names(position.get("code") for position in self._strategy_config.get("positions", []))
            for position in self._strategy_config.get("positions", []):
                item = QListWidgetItem(self._format_strategy_position(position))
                item.setData(Qt.UserRole, position)
                self.list_strategy_positions.addItem(item)
            self._load_strategy_profile_options()
            self.list_strategy_positions.blockSignals(False)
            if self.list_strategy_positions.count() > 0:
                if current_row is not None:
                    self.list_strategy_positions.setCurrentRow(max(0, min(current_row, self.list_strategy_positions.count() - 1)))
                else:
                    self.list_strategy_positions.setCurrentRow(-1)
                    self._on_strategy_position_selected(-1)
            else:
                self._clear_strategy_position_editor()
        finally:
            self._loading_strategy_editor = False
        self._refresh_strategy_preview()
        self._refresh_strategy_template_list()
        self._refresh_strategy_params_list()

    def _current_strategy_position_row(self):
        row = self.list_strategy_positions.currentRow()
        positions = getattr(self, "_strategy_config", {}).get("positions", [])
        return row if 0 <= row < len(positions) else -1

    def _clear_strategy_position_editor(self):
        self.edit_strategy_code.clear()
        self.spin_strategy_cost.setValue(0.0)
        self.edit_strategy_buy_date.clear()
        self.edit_strategy_note.clear()
        self.cmb_strategy_profile.clear()

    def _set_strategy_selection_visible(self, visible):
        visible = bool(visible)
        self.strategy_position_detail.setVisible(visible)
        self.strategy_config_group.setVisible(visible)
        self.lbl_strategy_scope.setVisible(visible)
        if not visible:
            self.lbl_strategy_scope.setText("请先选择持仓")

    def _load_strategy_profile_options(self, selected_id=""):
        self.cmb_strategy_profile.blockSignals(True)
        try:
            self.cmb_strategy_profile.clear()
            for profile in self._strategy_config.get("strategy_profiles", []):
                self.cmb_strategy_profile.addItem(profile.get("name", profile.get("id", "")), profile.get("id"))
            if selected_id:
                index = self.cmb_strategy_profile.findData(selected_id)
                if index >= 0:
                    self.cmb_strategy_profile.setCurrentIndex(index)
        finally:
            self.cmb_strategy_profile.blockSignals(False)

    def _current_strategy_profile(self):
        profile_id = self.cmb_strategy_profile.currentData()
        for profile in getattr(self, "_strategy_config", {}).get("strategy_profiles", []):
            if profile.get("id") == profile_id:
                return profile
        return None

    def _current_strategy_rules(self):
        row = self._current_strategy_position_row()
        positions = getattr(self, "_strategy_config", {}).get("positions", [])
        base_rules = dict(self._strategy_config.get("rules", {}))
        profile = self._current_strategy_profile()
        rules = dict(base_rules)
        if profile:
            rules.update(profile.get("rules") or {})
        if 0 <= row < len(positions) and isinstance(positions[row].get("rules"), dict) and positions[row].get("rules"):
            rules.update(positions[row].get("rules", {}))
        return rules

    def _load_strategy_rules(self, rules):
        rules = rules or {}
        self.chk_strategy_loss.setChecked(bool(rules.get("max_loss_enabled")))
        self.spin_strategy_loss.setValue(float(rules.get("max_loss_pct", 5.0)))
        self.chk_strategy_stock_ma5.setChecked(bool(rules.get("stock_ma5_break_enabled")))
        self.chk_strategy_index_ma5.setChecked(bool(rules.get("index_ma5_break_enabled")))
        self.chk_strategy_index_ma10.setChecked(bool(rules.get("index_ma10_break_enabled")))
        self.chk_strategy_trailing.setChecked(bool(rules.get("trailing_profit_enabled")))
        tiers = rules.get("trailing_tiers", [])
        for i, (profit, lock) in enumerate(zip(self.spin_strategy_tier_profit, self.spin_strategy_tier_lock)):
            tier = tiers[i] if i < len(tiers) else {}
            profit.setValue(float(tier.get("profit_pct", 0.0)))
            lock.setValue(float(tier.get("lock_pct", 0.0)))
        self.chk_strategy_skip_volume_drop.setChecked(bool(rules.get("skip_raise_on_volume_drop")))
        self.chk_strategy_reduce_half.setChecked(bool(rules.get("reduce_half_enabled")))
        self.spin_strategy_reduce_half.setValue(float(rules.get("reduce_half_profit_pct", 45.0)))
        self.chk_strategy_stale.setChecked(bool(rules.get("stale_position_enabled")))
        self.spin_strategy_stale_days.setValue(int(rules.get("stale_position_days", 12)))

    def _on_strategy_position_selected(self, row: int):
        positions = getattr(self, "_strategy_config", {}).get("positions", [])
        if row < 0 or row >= len(positions):
            self._open_strategy_position = False
            self._set_strategy_selection_visible(False)
            self._clear_strategy_position_editor()
            return
        self._open_strategy_position = True
        self._set_strategy_selection_visible(True)
        position = normalize_strategy_position(positions[row]) or {}
        self._loading_strategy_editor = True
        try:
            self.edit_strategy_code.setText(position.get("code", ""))
            self.spin_strategy_cost.setValue(float(position.get("cost_price", 0.0)))
            self.edit_strategy_buy_date.setText(position.get("buy_date", ""))
            self.edit_strategy_note.setText(position.get("note", ""))
            profile_id = position.get("strategy_id") or "default"
            self._load_strategy_profile_options(profile_id)
            rules = self._current_strategy_rules()
            self._load_strategy_rules(rules)
            profile = self._current_strategy_profile() or {}
            self.lbl_strategy_scope.setText(
                f"当前股票：{position.get('code', '')}    策略：{profile.get('name') or profile.get('id') or '未绑定'}"
            )
        finally:
            self._loading_strategy_editor = False
        self._strategy_save_baseline_row = row
        self._strategy_save_baseline_position = dict(position)
        self._refresh_strategy_preview()
        self._refresh_strategy_params_list()

    def _collect_strategy_rules_from_editor(self):
        return {
            "max_loss_enabled": self.chk_strategy_loss.isChecked(),
            "max_loss_pct": self.spin_strategy_loss.value(),
            "stock_ma5_break_enabled": self.chk_strategy_stock_ma5.isChecked(),
            "index_ma5_break_enabled": self.chk_strategy_index_ma5.isChecked(),
            "index_ma10_break_enabled": self.chk_strategy_index_ma10.isChecked(),
            "trailing_profit_enabled": self.chk_strategy_trailing.isChecked(),
            "trailing_tiers": [
                {"profit_pct": profit.value(), "lock_pct": lock.value()}
                for profit, lock in zip(self.spin_strategy_tier_profit, self.spin_strategy_tier_lock)
            ],
            "skip_raise_on_volume_drop": self.chk_strategy_skip_volume_drop.isChecked(),
            "reduce_half_enabled": self.chk_strategy_reduce_half.isChecked(),
            "reduce_half_profit_pct": self.spin_strategy_reduce_half.value(),
            "stale_position_enabled": self.chk_strategy_stale.isChecked(),
            "stale_position_days": self.spin_strategy_stale_days.value(),
        }

    def _collect_strategy_config_from_editor(self):
        current_rules = self._collect_strategy_rules_from_editor()
        positions = list(getattr(self, "_strategy_config", {}).get("positions", []))
        profiles = [dict(profile) for profile in getattr(self, "_strategy_config", {}).get("strategy_profiles", [])]
        row = self._current_strategy_position_row()
        if 0 <= row < len(positions):
            position = dict(positions[row])
            profile_id = self.cmb_strategy_profile.currentData() or position.get("strategy_id") or "default"
            position["strategy_id"] = profile_id
            position["rules"] = current_rules
            positions[row] = position
        return normalize_strategy_alert_config({
            "enabled": self.chk_strategy_enabled.isChecked(),
            "positions": positions,
            "strategy_profiles": profiles,
            "notifications": {
                "desktop_popup": self.chk_strategy_notify_desktop.isChecked(),
                "panel_highlight": self.chk_strategy_notify_panel.isChecked(),
                "remote_push": self.chk_strategy_notify_remote.isChecked(),
                "remote_channel": self.cmb_strategy_remote_channel.currentData() or "wecom",
                "webhook_url": self.edit_strategy_webhook.text().strip(),
                "daily_summary_time": "09:00,18:00",
            },
            "rules": getattr(self, "_strategy_config", {}).get("rules", {}),
        })

    def _on_strategy_config_changed(self, *_args):
        if getattr(self, "_loading_strategy_editor", False):
            return
        self._strategy_config = self._collect_strategy_config_from_editor()
        self._refresh_strategy_preview()
        self.win.set_strategy_alert_config(self._strategy_config)

    def _on_strategy_profile_selected(self, *_args):
        if getattr(self, "_loading_strategy_editor", False):
            return
        row = self._current_strategy_position_row()
        profile_id = self.cmb_strategy_profile.currentData()
        if row < 0 or not profile_id:
            return
        self._strategy_config["positions"][row]["strategy_id"] = profile_id
        self._strategy_config["positions"][row]["rules"] = {}
        self._loading_strategy_editor = True
        try:
            self._load_strategy_rules(self._current_strategy_rules())
        finally:
            self._loading_strategy_editor = False
        self._mark_pending_apply_alert(self._strategy_config["positions"][row].get("code", ""))
        self._refresh_strategy_preview()

    def _clone_strategy_profile(self):
        source = self._current_strategy_profile()
        if not source:
            return
        existing_ids = {profile.get("id") for profile in self._strategy_config.get("strategy_profiles", [])}
        number = 1
        profile_id = f"custom:{number}"
        while profile_id in existing_ids:
            number += 1
            profile_id = f"custom:{number}"
        profile = {
            "id": profile_id,
            "name": f"自定义规则组 {number}",
            "rules": dict(source.get("rules") or {}),
        }
        self._strategy_config["strategy_profiles"].append(profile)
        row = self._current_strategy_position_row()
        if row >= 0:
            self._strategy_config["positions"][row]["strategy_id"] = profile_id
            self._strategy_config["positions"][row]["rules"] = {}
            self._mark_pending_apply_alert(self._strategy_config["positions"][row].get("code", ""))
        self._load_strategy_profile_options(profile_id)
        self._load_strategy_rules(profile["rules"])
        self._refresh_strategy_preview()

    def _save_strategy_position(self):
        row = self._current_strategy_position_row()
        if row < 0:
            return
        # 保存前快照，用于检测条件/模板变化
        position = self._strategy_config["positions"][row]
        baseline = getattr(self, "_strategy_save_baseline_position", None)
        if getattr(self, "_strategy_save_baseline_row", -1) == row and isinstance(baseline, dict):
            position = dict(baseline)
        code = position.get("code", "")
        old_rules = dict(position.get("rules", {}))
        old_profile_id = position.get("strategy_id", "default")
        old_cost = float(position.get("cost_price") or 0.0)
        old_locked_pct = float(position.get("locked_profit_pct") or 0.0)
        old_config = dict(self._strategy_config)
        old_positions = list(old_config.get("positions", []))
        if 0 <= row < len(old_positions):
            old_positions[row] = position
        old_config["positions"] = old_positions
        old_resolved_rules = strategy_rules_for_position(old_config, position)
        old_stop_price = strategy_stop_price(old_cost, old_resolved_rules, old_locked_pct)
        was_first_apply = self._consume_pending_apply_alert(code)

        self._on_strategy_position_editor_changed()
        self._on_strategy_config_changed()

        new_position = self._strategy_config["positions"][row]
        new_rules = new_position.get("rules", {})
        new_profile_id = new_position.get("strategy_id", "default")
        new_cost = float(new_position.get("cost_price") or 0.0)
        new_locked_pct = float(new_position.get("locked_profit_pct") or 0.0)
        new_resolved_rules = strategy_rules_for_position(self._strategy_config, new_position)
        new_stop_price = strategy_stop_price(new_cost, new_resolved_rules, new_locked_pct)

        profile_changed = old_profile_id != new_profile_id
        if was_first_apply or profile_changed:
            # 第一次套用策略 或 切换模板：提醒止损线
            self._send_strategy_apply_alert(new_position, new_profile_id)
            if new_stop_price is not None:
                new_position["last_stop_price"] = round(float(new_stop_price), 4)
                self._strategy_config["positions"][row] = new_position
                self.win.set_strategy_alert_config(self._strategy_config)
        elif old_rules != new_rules:
            # 仅覆盖参数变更：提醒具体变化
            self._send_strategy_change_alert(new_position, old_rules, new_rules, old_profile_id, new_profile_id)
        previous_line = old_stop_price
        stored_line = new_position.get("last_stop_price", 0.0)
        try:
            if not self._strategy_line_changed(old_stop_price, new_stop_price) and float(stored_line) > 0:
                previous_line = float(stored_line)
        except Exception:
            pass
        if not was_first_apply and self._strategy_line_changed(previous_line, new_stop_price):
            self._send_strategy_line_change_alert(new_position, old_cost, new_cost, previous_line, new_stop_price)
            if new_stop_price is not None:
                new_position["last_stop_price"] = round(float(new_stop_price), 4)
                self._strategy_config["positions"][row] = new_position
                self.win.set_strategy_alert_config(self._strategy_config)

        self._strategy_save_baseline_row = row
        self._strategy_save_baseline_position = dict(self._strategy_config["positions"][row])

        self.btn_strategy_save.setText("已保存")
        QTimer.singleShot(1200, lambda: self.btn_strategy_save.setText("保存当前持仓"))

    # ---- 策略套用 / 止损线提醒辅助 ----

    def _mark_pending_apply_alert(self, code):
        codes = getattr(self, "_pending_apply_alert_codes", None)
        if codes is None:
            codes = set()
            self._pending_apply_alert_codes = codes
        if code:
            codes.add(code)

    def _consume_pending_apply_alert(self, code):
        codes = getattr(self, "_pending_apply_alert_codes", None)
        if not codes or not code:
            return False
        if code in codes:
            codes.discard(code)
            return True
        return False

    @staticmethod
    def _strategy_line_changed(old_price, new_price):
        try:
            if old_price is None or new_price is None:
                return old_price != new_price
            return abs(float(old_price) - float(new_price)) > 0.0001
        except Exception:
            return old_price != new_price

    def _strategy_alert_stock_name(self, code):
        names = getattr(self.win, "code_names", {})
        if not isinstance(names, dict):
            names = {}
        return str(names.get(code) or code or "").strip()

    @staticmethod
    def _strategy_line_label_for_position(position):
        try:
            return "止盈线" if float(position.get("locked_profit_pct") or 0.0) > 0 else "止损线"
        except Exception:
            return "止损线"

    def _send_strategy_line_change_alert(self, position, old_cost, new_cost, old_stop_price, new_stop_price):
        code = position.get("code", "")
        old_line = "-" if old_stop_price is None else f"{float(old_stop_price):.2f}"
        new_line = "-" if new_stop_price is None else f"{float(new_stop_price):.2f}"
        line_label = self._strategy_line_label_for_position(position)
        stock_name = self._strategy_alert_stock_name(code)
        alert_text = (
            f"## {stock_name}{line_label}变化\n"
            f">标的：{stock_name}\n"
            f">代码：{code}\n"
            f"\n"
            f">变动：\n"
            f">成本价：{float(old_cost):.3f} -> {float(new_cost):.3f}\n"
            f">{line_label}：{old_line} -> {new_line}"
        )
        self._send_desktop_alert(alert_text)
        self._record_strategy_settings_history(position, f"{line_label}变化", "warning")

    def _send_strategy_apply_alert(self, position, profile_id):
        """股票套用/切换策略时，发送止损线提醒"""
        code = position.get("code", "")
        cost = float(position.get("cost_price") or 0.0)
        if cost <= 0:
            return
        rules = strategy_rules_for_position(self._strategy_config, position)
        stop_price = strategy_stop_price(cost, rules, 0.0)
        if stop_price is None:
            return
        max_loss_pct = float(rules.get("max_loss_pct", 0.0))
        profile = self._get_profile_by_id(profile_id)
        profile_name = profile.get("name", profile_id) if profile else profile_id
        stock_name = self._strategy_alert_stock_name(code)
        alert_text = (
            f"## {stock_name}策略套用\n"
            f">标的：{stock_name}\n"
            f">代码：{code}\n"
            f"\n"
            f">策略模板：{profile_name}\n"
            f">成本价：{cost:.2f}\n"
            f">止损线：{stop_price:.2f}（止损 -{max_loss_pct:.1f}%）"
        )
        self._send_desktop_alert(alert_text)
        self._record_strategy_settings_history(position, "策略套用", "warning")

    def _send_strategy_change_alert(self, position, old_rules, new_rules, old_profile_id, new_profile_id):
        """发送策略条件修改提醒"""
        code = position.get("code", "")
        changes = []
        
        # 检测模板变化
        if old_profile_id != new_profile_id:
            old_profile = self._get_profile_by_id(old_profile_id)
            new_profile = self._get_profile_by_id(new_profile_id)
            old_name = old_profile.get("name", old_profile_id) if old_profile else old_profile_id
            new_name = new_profile.get("name", new_profile_id) if new_profile else new_profile_id
            changes.append(f"策略模板：{old_name} → {new_name}")
        
        # 检测规则变化
        if old_rules != new_rules:
            rule_changes = self._compare_rules(old_rules, new_rules)
            changes.extend(rule_changes)

        # 若涉及止损，附上当前止损价
        if (old_rules.get("max_loss_enabled") or new_rules.get("max_loss_enabled")) and changes:
            cost = float(position.get("cost_price") or 0.0)
            if cost > 0:
                resolved = strategy_rules_for_position(self._strategy_config, position)
                stop = strategy_stop_price(cost, resolved, 0.0)
                if stop is not None:
                    changes.append(f"当前止损线：{stop:.2f}")

        if changes:
            change_text = "\n".join(f"• {c}" for c in changes)
            stock_name = self._strategy_alert_stock_name(code)
            alert_text = (
                f"## {stock_name}策略修改\n"
                f">标的：{stock_name}\n"
                f">代码：{code}\n"
                f"\n"
                f">修改内容：\n{change_text}"
            )
            self._send_desktop_alert(alert_text)
            self._record_strategy_settings_history(position, "策略修改", "warning")

    def _record_strategy_settings_history(self, position, status, severity="warning"):
        code = normalize_code_or_none(position.get("code")) or str(position.get("code") or "")
        item = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "code": code,
            "name": self._strategy_alert_stock_name(code),
            "status": str(status or "").strip(),
            "severity": str(severity or "warning").strip(),
        }
        history = [item]
        for old in getattr(self.win, "strategy_alert_history", []):
            if old.get("code") == item["code"] and old.get("status") == item["status"] and old.get("time") == item["time"]:
                continue
            history.append(old)
            if len(history) >= 50:
                break
        self.win.strategy_alert_history = history
        notifier = getattr(self.win, "_notify_change", None)
        if callable(notifier):
            notifier()
        self._refresh_strategy_history()

    def _get_profile_by_id(self, profile_id):
        """根据ID获取策略模板"""
        for profile in self._strategy_config.get("strategy_profiles", []):
            if profile.get("id") == profile_id:
                return profile
        return None

    def _compare_rules(self, old_rules, new_rules):
        """比较规则变化并生成提醒文本"""
        changes = []
        
        # 止盈相关
        if old_rules.get("max_loss_enabled") != new_rules.get("max_loss_enabled"):
            status = "启用" if new_rules.get("max_loss_enabled") else "禁用"
            changes.append(f"浮亏清仓提醒：{status}")
        elif old_rules.get("max_loss_pct") != new_rules.get("max_loss_pct"):
            changes.append(f"浮亏清仓阈值：{old_rules.get('max_loss_pct', 0):.1f}% → {new_rules.get('max_loss_pct', 0):.1f}%")
        
        if old_rules.get("reduce_half_enabled") != new_rules.get("reduce_half_enabled"):
            status = "启用" if new_rules.get("reduce_half_enabled") else "禁用"
            changes.append(f"盈利减半提醒：{status}")
        elif old_rules.get("reduce_half_profit_pct") != new_rules.get("reduce_half_profit_pct"):
            changes.append(f"盈利减半阈值：{old_rules.get('reduce_half_profit_pct', 0):.1f}% → {new_rules.get('reduce_half_profit_pct', 0):.1f}%")
        
        if old_rules.get("trailing_profit_enabled") != new_rules.get("trailing_profit_enabled"):
            status = "启用" if new_rules.get("trailing_profit_enabled") else "禁用"
            changes.append(f"阶梯移动止盈：{status}")
        
        # 止损相关
        if old_rules.get("stock_ma5_break_enabled") != new_rules.get("stock_ma5_break_enabled"):
            status = "启用" if new_rules.get("stock_ma5_break_enabled") else "禁用"
            changes.append(f"个股破5日线止损：{status}")
        
        if old_rules.get("index_ma5_break_enabled") != new_rules.get("index_ma5_break_enabled"):
            status = "启用" if new_rules.get("index_ma5_break_enabled") else "禁用"
            changes.append(f"大盘破5日线风控：{status}")
        
        if old_rules.get("index_ma10_break_enabled") != new_rules.get("index_ma10_break_enabled"):
            status = "启用" if new_rules.get("index_ma10_break_enabled") else "禁用"
            changes.append(f"大盘破10日线风控：{status}")
        
        if old_rules.get("stale_position_enabled") != new_rules.get("stale_position_enabled"):
            status = "启用" if new_rules.get("stale_position_enabled") else "禁用"
            changes.append(f"持仓时间提醒：{status}")
        elif old_rules.get("stale_position_days") != new_rules.get("stale_position_days"):
            changes.append(f"持仓时间提醒：{old_rules.get('stale_position_days', 0)}天 → {new_rules.get('stale_position_days', 0)}天")
        
        return changes

    def _send_desktop_alert(self, text):
        """发送桌面提醒"""
        notifications = normalize_strategy_alert_config(getattr(self, "_strategy_config", {}))["notifications"]
        if notifications.get("desktop_popup"):
            # 调用主窗口的提醒功能
            if hasattr(self.win, "show_desktop_alert"):
                self.win.show_desktop_alert(text)
        if notifications.get("remote_push"):
            # 发送远程推送
            if hasattr(self.win, "_send_strategy_push_text"):
                self.win._send_strategy_push_text(text)

    def _refresh_strategy_preview(self):
        if not hasattr(self, "list_strategy_preview"):
            return
        if self._current_strategy_position_row() < 0:
            self.list_strategy_preview.clear()
            self.list_strategy_preview.addItem(QListWidgetItem("请先选择持仓查看对应策略"))
            self._refresh_strategy_history()
            return
        config = normalize_strategy_alert_config(getattr(self, "_strategy_config", {}))
        rules = self._current_strategy_rules()
        notifications = config["notifications"]
        channels = []
        if notifications.get("desktop_popup"):
            channels.append("桌面弹窗")
        if notifications.get("panel_highlight"):
            channels.append("浮窗高亮")
        if notifications.get("remote_push"):
            channels.append("远程推送")
        channel_text = "、".join(channels) if channels else "未选择提醒方式"

        rows = []
        if not config.get("enabled"):
            rows.append("策略提醒未启用")
        elif not config.get("positions"):
            rows.append(f"启用后使用：{channel_text}；请先添加持仓")
        else:
            rows.append(f"触发后使用：{channel_text}")
            if notifications.get("remote_push") and not notifications.get("webhook_url"):
                rows.append("远程推送未配置Webhook地址")
            elif notifications.get("remote_push"):
                rows.append("交易日 09:00、18:00 远程推送：当前持仓止损/止盈摘要")
                rows.append(f"同一状态 {int(notifications.get('push_cooldown_minutes', 30))} 分钟内不重复推送")
            if rules.get("max_loss_enabled"):
                rows.append(f"持仓浮亏达到 {float(rules.get('max_loss_pct', 0.0)):.1f}%：提醒清仓")
            if rules.get("stock_ma5_break_enabled"):
                rows.append("个股跌破5日线：提醒卖出")
            if rules.get("index_ma5_break_enabled") or rules.get("index_ma10_break_enabled"):
                lines = []
                if rules.get("index_ma5_break_enabled"):
                    lines.append("5日线")
                if rules.get("index_ma10_break_enabled"):
                    lines.append("10日线")
                rows.append(f"大盘跌破{'/'.join(lines)}：提醒全仓卖出")
            if rules.get("trailing_profit_enabled"):
                tiers = ", ".join(
                    f"{float(tier.get('profit_pct', 0.0)):.0f}%锁{float(tier.get('lock_pct', 0.0)):.0f}%"
                    for tier in rules.get("trailing_tiers", [])
                )
                rows.append(f"阶梯移动止盈：{tiers}")
            if rules.get("reduce_half_enabled"):
                rows.append(f"盈利达到 {float(rules.get('reduce_half_profit_pct', 0.0)):.1f}%：提醒减半仓")
            if rules.get("stale_position_enabled"):
                rows.append(f"持仓满 {int(rules.get('stale_position_days', 0))} 天不上涨：提醒卖出")

        self.list_strategy_preview.clear()
        for row in rows:
            self.list_strategy_preview.addItem(QListWidgetItem(row))
        self._refresh_strategy_history()

    def _refresh_strategy_history(self):
        if not hasattr(self, "list_strategy_history"):
            return
        self.list_strategy_history.clear()
        history = getattr(self.win, "strategy_alert_history", [])
        if not history:
            self.list_strategy_history.addItem(QListWidgetItem("暂无触发记录"))
            return
        shown = 0
        for item in history:
            text = f"{item.get('time', '')} {item.get('name') or item.get('code')} {item.get('status', '')}".strip()
            self.list_strategy_history.addItem(QListWidgetItem(text))
            shown += 1
            if shown >= 50:
                break

    def _install_wheel_guards(self):
        for widget in self.findChildren(QSpinBox) + self.findChildren(QDoubleSpinBox):
            widget.setFocusPolicy(Qt.StrongFocus)
            widget.installEventFilter(self)
        for widget in self.findChildren(QComboBox):
            widget.setFocusPolicy(Qt.StrongFocus)
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)) and event.type() == QEvent.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    def _on_strategy_position_editor_changed(self, *_args):
        if getattr(self, "_loading_strategy_editor", False):
            return
        row = self._current_strategy_position_row()
        if row < 0:
            return
        previous = self._strategy_config["positions"][row]
        code = normalize_code_or_none(self.edit_strategy_code.text())
        if code not in self._strategy_allowed_codes():
            self.edit_strategy_code.setText(previous.get("code", ""))
            return
        position = normalize_strategy_position({
            "code": code,
            "strategy_id": self.cmb_strategy_profile.currentData() or previous.get("strategy_id", "default"),
            "cost_price": self.spin_strategy_cost.value(),
            "buy_date": self.edit_strategy_buy_date.text(),
            "note": self.edit_strategy_note.text(),
            "peak_profit_pct": previous.get("peak_profit_pct", 0.0),
            "locked_profit_pct": previous.get("locked_profit_pct", 0.0),
            "last_stop_price": previous.get("last_stop_price", 0.0),
            "rules": previous.get("rules", {}),
        })
        if not position:
            return
        self._strategy_config["positions"][row] = position
        item = self.list_strategy_positions.item(row)
        if item:
            item.setText(self._format_strategy_position(position))
            item.setData(Qt.UserRole, position)
        self._on_strategy_config_changed()

    def _add_strategy_position(self):
        config = normalize_strategy_alert_config(getattr(self, "_strategy_config", {}))
        selected_code = self._current_code_from_tree()
        allowed_codes = list(normalize_codes(getattr(self.win, "codes", [])))
        default_code = selected_code if selected_code in allowed_codes else (allowed_codes[0] if allowed_codes else "")
        if not default_code:
            return
        config["positions"].append({
            "code": default_code,
            "strategy_id": "default",
            "cost_price": 0.0,
            "buy_date": date.today().strftime("%Y-%m-%d"),
            "note": "",
            "rules": {},
        })
        self.win.set_strategy_alert_config(config)
        self._strategy_config = config
        self._load_strategy_config(len(config["positions"]) - 1)
        # 新持仓首次保存时提醒止损线
        self._mark_pending_apply_alert(default_code)

    def _del_strategy_position(self):
        row = self._current_strategy_position_row()
        if row < 0:
            return
        config = normalize_strategy_alert_config(getattr(self, "_strategy_config", {}))
        if 0 <= row < len(config["positions"]):
            config["positions"].pop(row)
        self.win.set_strategy_alert_config(config)
        self._strategy_config = config
        self._load_strategy_config(max(0, row - 1))

    def _on_strategy_params_edit(self):
        self.list_strategy_params.setVisible(False)
        self.strategy_params_editor.setVisible(True)
        self.btn_strategy_params_edit.setVisible(False)
        self.btn_strategy_params_save.setVisible(True)

    def _on_strategy_params_save(self):
        self.strategy_params_editor.setVisible(False)
        self.list_strategy_params.setVisible(True)
        self.btn_strategy_params_edit.setVisible(True)
        self.btn_strategy_params_save.setVisible(False)
        self._save_strategy_position()
        self._refresh_strategy_params_list()

    def _on_strategy_template_reset(self):
        row = self._current_strategy_position_row()
        if row < 0:
            return
        self._strategy_config["positions"][row]["rules"] = {}
        self._on_strategy_config_changed()
        self._load_strategy_rules(self._current_strategy_rules())
        self._refresh_strategy_params_list()

    def _on_strategy_template_selected(self, row: int):
        profiles = getattr(self, "_strategy_config", {}).get("strategy_profiles", [])
        if row < 0 or row >= len(profiles):
            self.edit_template_name.clear()
            self.edit_template_desc.clear()
            self.lbl_template_ref_count.setText("被引用：0 只股票")
            self._load_template_rules_to_editor({})
            self._load_template_action_rules([])
            self.template_rules_scroll.setVisible(True)
            self.template_action_group.setVisible(False)
            self._set_template_editor_mode("default")
            return
        profile = profiles[row]
        self.edit_template_name.setText(profile.get('name', ''))
        self.edit_template_desc.setText(profile.get('desc', ''))
        positions = getattr(self, "_strategy_config", {}).get("positions", [])
        ref_count = sum(1 for p in positions if p.get("strategy_id") == profile.get("id"))
        self.lbl_template_ref_count.setText(f"被引用：{ref_count} 只股票")
        action_rules = profile.get("action_rules") if isinstance(profile.get("action_rules"), list) else []
        if profile.get("strategy_type") == "turtle":
            self.template_rules_scroll.setVisible(True)
            self.template_action_group.setVisible(False)
            self._set_template_editor_mode("turtle")
            self._load_turtle_params_to_editor(profile.get("turtle_params", {}))
            self._load_template_action_rules(action_rules)
        else:
            self.template_rules_scroll.setVisible(True)
            self.template_action_group.setVisible(False)
            self._set_template_editor_mode("default")
            self._load_template_action_rules([])
            self._load_template_rules_to_editor(profile.get("rules", {}))

    def _set_template_editor_mode(self, mode):
        is_turtle = mode == "turtle"
        for widget in (self.g_template_profit, self.g_template_loss, self.g_template_position):
            widget.setVisible(not is_turtle)
        self.g_template_turtle.setVisible(is_turtle)

    def _on_template_new(self):
        profiles = self._strategy_config.get("strategy_profiles", [])
        existing_ids = {p.get("id") for p in profiles}
        number = 1
        profile_id = f"template:{number}"
        while profile_id in existing_ids:
            number += 1
            profile_id = f"template:{number}"
        new_profile = {
            "id": profile_id,
            "name": f"新建模板 {number}",
            "desc": "",
            "rules": dict(self._strategy_config.get("rules", {})),
        }
        profiles.append(new_profile)
        self._strategy_config["strategy_profiles"] = profiles
        self.win.set_strategy_alert_config(self._strategy_config)
        self._refresh_strategy_template_list()
        self._refresh_strategy_params_list()

    def _on_template_save(self):
        row = self.list_strategy_templates.currentRow()
        profiles = self._strategy_config.get("strategy_profiles", [])
        if row < 0 or row >= len(profiles):
            return
        profile = profiles[row]
        profile["name"] = self.edit_template_name.text().strip() or profile.get("name", "未命名")
        profile["desc"] = self.edit_template_desc.text().strip()
        if profile.get("strategy_type") == "turtle":
            params = self._collect_turtle_params_from_editor()
            profile["turtle_params"] = params
            profile["action_rules"] = default_turtle_action_rules(params)
        else:
            profile["rules"] = self._collect_template_rules_from_editor()
        self._strategy_config["strategy_profiles"] = profiles
        self.win.set_strategy_alert_config(self._strategy_config)
        self._refresh_strategy_template_list()
        self.list_strategy_templates.setCurrentRow(row)
        self.btn_template_save.setText("已保存")
        QTimer.singleShot(1200, lambda: self.btn_template_save.setText("保存模板"))

    def _on_template_rules_changed(self, *_args):
        # 模板规则编辑区内容变化时，可以实时预览或标记为未保存
        pass

    def _collect_template_rules_from_editor(self):
        return {
            "max_loss_enabled": self.chk_template_loss.isChecked(),
            "max_loss_pct": self.spin_template_loss.value(),
            "stock_ma5_break_enabled": self.chk_template_stock_ma5.isChecked(),
            "index_ma5_break_enabled": self.chk_template_index_ma5.isChecked(),
            "index_ma10_break_enabled": self.chk_template_index_ma10.isChecked(),
            "trailing_profit_enabled": self.chk_template_trailing.isChecked(),
            "trailing_tiers": [
                {"profit_pct": profit.value(), "lock_pct": lock.value()}
                for profit, lock in zip(self.spin_template_tier_profit, self.spin_template_tier_lock)
            ],
            "skip_raise_on_volume_drop": self.chk_template_skip_volume_drop.isChecked(),
            "reduce_half_enabled": self.chk_template_reduce_half.isChecked(),
            "reduce_half_profit_pct": self.spin_template_reduce_half.value(),
            "stale_position_enabled": self.chk_template_stale.isChecked(),
            "stale_position_days": self.spin_template_stale_days.value(),
        }

    def _load_template_rules_to_editor(self, rules):
        rules = rules or {}
        self.chk_template_loss.setChecked(bool(rules.get("max_loss_enabled")))
        self.spin_template_loss.setValue(float(rules.get("max_loss_pct", 5.0)))
        self.chk_template_stock_ma5.setChecked(bool(rules.get("stock_ma5_break_enabled")))
        self.chk_template_index_ma5.setChecked(bool(rules.get("index_ma5_break_enabled")))
        self.chk_template_index_ma10.setChecked(bool(rules.get("index_ma10_break_enabled")))
        self.chk_template_trailing.setChecked(bool(rules.get("trailing_profit_enabled")))
        tiers = rules.get("trailing_tiers", [])
        for i, (profit, lock) in enumerate(zip(self.spin_template_tier_profit, self.spin_template_tier_lock)):
            tier = tiers[i] if i < len(tiers) else {}
            profit.setValue(float(tier.get("profit_pct", 0.0)))
            lock.setValue(float(tier.get("lock_pct", 0.0)))
        self.chk_template_skip_volume_drop.setChecked(bool(rules.get("skip_raise_on_volume_drop")))
        self.chk_template_reduce_half.setChecked(bool(rules.get("reduce_half_enabled")))
        self.spin_template_reduce_half.setValue(float(rules.get("reduce_half_profit_pct", 45.0)))
        self.chk_template_stale.setChecked(bool(rules.get("stale_position_enabled")))
        self.spin_template_stale_days.setValue(int(rules.get("stale_position_days", 12)))

    def _format_template_action_rule(self, rule):
        rule = normalize_strategy_action_rule(rule)
        condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
        threshold = condition.get("threshold") if isinstance(condition.get("threshold"), dict) else {}
        action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
        parameter = rule.get("parameter") if isinstance(rule.get("parameter"), dict) else {}
        name = str(rule.get("name") or rule.get("id") or "动作规则")
        action_type = str(action.get("type") or "-")
        threshold_type = str(threshold.get("type") or "")
        unit_labels = {
            "percent": "%",
            "price": "元",
            "atr": "ATR",
            "day_high": "日新高",
            "day_low": "日低点",
            "ma_days": "日线MA",
            "days": "天",
            "trend": "趋势",
        }
        action_labels = {
            "entry_signal": "提醒观察/买入",
            "clear_position": "提醒清仓",
            "add_position": "提醒加仓",
            "reduce_position": "提醒减仓",
            "update_stop_line": "提醒止盈线变化",
            "block_open": "禁止新开仓",
        }
        try:
            value_text = f"{float(parameter.get('value', 0.0)):g}"
        except Exception:
            value_text = "0"
        unit_text = unit_labels.get(parameter.get("unit"), parameter.get("unit") or threshold_type or "-")
        return f"{name} | {condition.get('metric', '-')} {condition.get('operator', '-')} {value_text}{unit_text} -> {action_labels.get(action_type, action_type)}"

    def _combo_with_data(self, pairs, current_data):
        combo = QComboBox()
        for label, data in pairs:
            combo.addItem(label, data)
        idx = combo.findData(current_data)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setMinimumWidth(86)
        return combo

    def _load_template_action_rules(self, action_rules):
        self._template_action_rules = [normalize_strategy_action_rule(rule) for rule in (action_rules or []) if isinstance(rule, dict)]
        self.list_template_action_rules.clear()
        for rule in self._template_action_rules:
            if rule.get("enabled", True):
                self.list_template_action_rules.addItem(QListWidgetItem(self._format_template_action_rule(rule)))
        if self.list_template_action_rules.count() == 0:
            self.list_template_action_rules.addItem(QListWidgetItem("暂无动作规则"))
        self._load_template_action_rule_table(self._template_action_rules)

    def _load_template_action_rule_table(self, action_rules):
        self.table_template_action_rules.blockSignals(True)
        self.table_template_action_rules.setRowCount(0)
        metric_options = [
            ("浮盈/浮亏", "profit_pct"),
            ("最高浮盈", "peak_profit_pct"),
            ("当前价", "stock_price"),
            ("大盘价", "index_price"),
            ("持仓天数", "holding_days"),
            ("大盘趋势", "index_ma_trend"),
        ]
        operator_options = [("达到/大于等于", ">="), ("小于等于", "<="), ("大于", ">"), ("小于", "<"), ("等于", "is")]
        unit_options = [
            ("%", "percent"),
            ("元", "price"),
            ("ATR", "atr"),
            ("日新高", "day_high"),
            ("日低点", "day_low"),
            ("日线MA", "ma_days"),
            ("天", "days"),
            ("趋势", "trend"),
        ]
        action_options = [
            ("提醒观察/买入", "entry_signal"),
            ("提醒清仓", "clear_position"),
            ("提醒加仓", "add_position"),
            ("提醒减仓", "reduce_position"),
            ("提醒止盈线变化", "update_stop_line"),
            ("禁止新开仓", "block_open"),
        ]
        for rule in action_rules:
            row = self.table_template_action_rules.rowCount()
            self.table_template_action_rules.insertRow(row)
            chk = QCheckBox()
            chk.setChecked(bool(rule.get("enabled", True)))
            self.table_template_action_rules.setCellWidget(row, 0, chk)
            condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
            parameter = rule.get("parameter") if isinstance(rule.get("parameter"), dict) else {}
            action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
            self.table_template_action_rules.setCellWidget(row, 1, self._combo_with_data(metric_options, condition.get("metric", "stock_price")))
            self.table_template_action_rules.setCellWidget(row, 2, self._combo_with_data(operator_options, condition.get("operator", ">=")))
            spin = QDoubleSpinBox()
            spin.setRange(-100000.0, 100000.0)
            spin.setDecimals(2)
            spin.setFixedWidth(82)
            try:
                spin.setValue(float(parameter.get("value", 0.0)))
            except Exception:
                spin.setValue(0.0)
            self.table_template_action_rules.setCellWidget(row, 3, spin)
            self.table_template_action_rules.setCellWidget(row, 4, self._combo_with_data(unit_options, parameter.get("unit", "percent")))
            self.table_template_action_rules.setCellWidget(row, 5, self._combo_with_data(action_options, action.get("type", "clear_position")))
            extra = QSpinBox()
            extra.setRange(0, 999)
            extra.setFixedWidth(70)
            extra.setToolTip("加仓规则使用最大份数，其他规则可留 0")
            extra.setValue(int(action.get("max_units", 0) or 0))
            self.table_template_action_rules.setCellWidget(row, 6, extra)
            item = QTableWidgetItem(str(rule.get("id") or ""))
            item.setData(Qt.UserRole, rule)
            self.table_template_action_rules.setVerticalHeaderItem(row, item)
        self.table_template_action_rules.blockSignals(False)

    def _collect_template_action_rules_from_table(self):
        result = []
        for row in range(self.table_template_action_rules.rowCount()):
            header = self.table_template_action_rules.verticalHeaderItem(row)
            original = header.data(Qt.UserRole) if header is not None else {}
            original = original if isinstance(original, dict) else {}
            enabled = self.table_template_action_rules.cellWidget(row, 0).isChecked()
            metric = self.table_template_action_rules.cellWidget(row, 1).currentData()
            operator = self.table_template_action_rules.cellWidget(row, 2).currentData()
            value = self.table_template_action_rules.cellWidget(row, 3).value()
            unit = self.table_template_action_rules.cellWidget(row, 4).currentData()
            action_type = self.table_template_action_rules.cellWidget(row, 5).currentData()
            max_units = self.table_template_action_rules.cellWidget(row, 6).value()
            rule = dict(original)
            rule["enabled"] = enabled
            old_condition = original.get("condition") if isinstance(original.get("condition"), dict) else {}
            rule["condition"] = {"metric": metric, "operator": operator, "threshold": dict(old_condition.get("threshold") or {})}
            rule["parameter"] = {"value": value, "unit": unit}
            action = dict(original.get("action") or {})
            action["type"] = action_type
            if action_type == "add_position":
                action["max_units"] = max_units
            else:
                action.pop("max_units", None)
            rule["action"] = action
            result.append(normalize_strategy_action_rule(rule))
        return result

    def _load_turtle_params_to_editor(self, params):
        params = params if isinstance(params, dict) else {}
        self.spin_turtle_entry_days.setValue(int(params.get("entry_days", 20)))
        self.spin_turtle_exit_days.setValue(int(params.get("exit_days", 10)))
        self.spin_turtle_atr_stop.setValue(float(params.get("atr_stop_multiple", 2.0)))
        self.spin_turtle_pyramid_atr.setValue(float(params.get("pyramid_atr_multiple", 0.5)))
        self.spin_turtle_max_units.setValue(int(params.get("max_units", 4)))
        sizing = str(params.get("position_sizing") or "atr_risk")
        index = self.cmb_turtle_sizing.findData(sizing)
        self.cmb_turtle_sizing.setCurrentIndex(index if index >= 0 else 0)

    def _collect_turtle_params_from_editor(self):
        return {
            "entry_days": self.spin_turtle_entry_days.value(),
            "exit_days": self.spin_turtle_exit_days.value(),
            "atr_stop_multiple": self.spin_turtle_atr_stop.value(),
            "pyramid_atr_multiple": self.spin_turtle_pyramid_atr.value(),
            "max_units": self.spin_turtle_max_units.value(),
            "position_sizing": self.cmb_turtle_sizing.currentData() or "atr_risk",
        }

    def _turtle_params_from_action_rules(self, action_rules, fallback=None):
        params = dict(fallback or {})
        for rule in action_rules or []:
            parameter = rule.get("parameter") if isinstance(rule.get("parameter"), dict) else {}
            action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
            value = parameter.get("value", 0)
            rule_id = rule.get("id")
            if rule_id == "turtle_entry_20d":
                params["entry_days"] = int(value)
            elif rule_id == "turtle_exit_10d":
                params["exit_days"] = int(value)
            elif rule_id == "turtle_atr_stop":
                params["atr_stop_multiple"] = float(value)
            elif rule_id == "turtle_pyramid_0_5atr":
                params["pyramid_atr_multiple"] = float(value)
                params["max_units"] = int(action.get("max_units", params.get("max_units", 4)) or 4)
        params.setdefault("position_sizing", self.cmb_turtle_sizing.currentData() or "atr_risk")
        return params

    def _on_template_copy(self):
        row = self.list_strategy_templates.currentRow()
        profiles = self._strategy_config.get("strategy_profiles", [])
        if row < 0 or row >= len(profiles):
            return
        source = profiles[row]
        existing_ids = {p.get("id") for p in profiles}
        number = 1
        profile_id = f"template:{number}"
        while profile_id in existing_ids:
            number += 1
            profile_id = f"template:{number}"
        new_profile = {
            "id": profile_id,
            "name": f"{source.get('name', '模板')} 副本",
            "desc": source.get("desc", ""),
            "rules": dict(source.get("rules", {})),
        }
        profiles.append(new_profile)
        self._strategy_config["strategy_profiles"] = profiles
        self.win.set_strategy_alert_config(self._strategy_config)
        self._refresh_strategy_template_list()

    def _on_template_delete(self):
        row = self.list_strategy_templates.currentRow()
        profiles = self._strategy_config.get("strategy_profiles", [])
        if row < 0 or row >= len(profiles):
            return
        profile = profiles[row]
        if profile.get("id") == "default":
            return
        # 检查是否有持仓引用该模板
        positions = self._strategy_config.get("positions", [])
        ref_count = sum(1 for p in positions if p.get("strategy_id") == profile.get("id"))
        if ref_count > 0:
            return
        profiles.pop(row)
        self._strategy_config["strategy_profiles"] = profiles
        self.win.set_strategy_alert_config(self._strategy_config)
        self._refresh_strategy_template_list()

    def _on_condition_add(self):
        indicator = self.cmb_condition_indicator.currentText()
        operator = self.cmb_condition_operator.currentText()
        threshold = self.edit_condition_threshold.text().strip()
        action = self.cmb_condition_action.currentText()
        logic = "且" if self.radio_logic_and.isChecked() else "或"
        if not threshold:
            return
        condition_text = f"[{logic}] {indicator} {operator} {threshold} → {action}"
        self.list_condition_rules.addItem(condition_text)
        self.edit_condition_threshold.clear()

    def _on_condition_remove(self, item):
        row = self.list_condition_rules.row(item)
        self.list_condition_rules.takeItem(row)

    def _refresh_strategy_params_list(self):
        self.list_strategy_params.clear()
        row = self._current_strategy_position_row()
        if row < 0:
            self.list_strategy_params.addItem("请先选择持仓")
            return
        rules = self._current_strategy_rules()
        base_rules = self._strategy_config.get("rules", {})
        profile = self._current_strategy_profile()
        profile_rules = profile.get("rules", {}) if profile else {}
        position_rules = self._strategy_config["positions"][row].get("rules", {})

        def param_status(key, current_value, default_value):
            if key in position_rules:
                return "已覆盖"
            elif key in profile_rules:
                return "继承模板"
            else:
                return "继承默认"

        params = [
            ("浮亏清仓阈值", f"{rules.get('max_loss_pct', 0):.1f}%", param_status("max_loss_pct", rules.get("max_loss_pct"), base_rules.get("max_loss_pct"))),
            ("盈利减半阈值", f"{rules.get('reduce_half_profit_pct', 0):.1f}%", param_status("reduce_half_profit_pct", rules.get("reduce_half_profit_pct"), base_rules.get("reduce_half_profit_pct"))),
            ("个股破线止损", "启用" if rules.get("stock_ma5_break_enabled") else "禁用", param_status("stock_ma5_break_enabled", rules.get("stock_ma5_break_enabled"), base_rules.get("stock_ma5_break_enabled"))),
            ("大盘5日线风控", "启用" if rules.get("index_ma5_break_enabled") else "禁用", param_status("index_ma5_break_enabled", rules.get("index_ma5_break_enabled"), base_rules.get("index_ma5_break_enabled"))),
            ("大盘10日线风控", "启用" if rules.get("index_ma10_break_enabled") else "禁用", param_status("index_ma10_break_enabled", rules.get("index_ma10_break_enabled"), base_rules.get("index_ma10_break_enabled"))),
            ("放量保护", "启用" if rules.get("skip_raise_on_volume_drop") else "禁用", param_status("skip_raise_on_volume_drop", rules.get("skip_raise_on_volume_drop"), base_rules.get("skip_raise_on_volume_drop"))),
            ("持仓时间提醒", f"{rules.get('stale_position_days', 0)}天", param_status("stale_position_days", rules.get("stale_position_days"), base_rules.get("stale_position_days"))),
        ]
        for name, value, status in params:
            item = QListWidgetItem(f"{name}：{value}  [{status}]")
            if status == "已覆盖":
                item.setForeground(QColor("#d97706"))
            elif status == "继承模板":
                item.setForeground(QColor("#2563eb"))
            else:
                item.setForeground(QColor("#6b7280"))
            self.list_strategy_params.addItem(item)

    def _refresh_strategy_template_list(self):
        self.list_strategy_templates.clear()
        profiles = self._strategy_config.get("strategy_profiles", [])
        positions = self._strategy_config.get("positions", [])
        for profile in profiles:
            ref_count = sum(1 for p in positions if p.get("strategy_id") == profile.get("id"))
            action_rules = profile.get("action_rules") if isinstance(profile.get("action_rules"), list) else []
            if action_rules:
                rule_count = len([rule for rule in action_rules if isinstance(rule, dict) and rule.get("enabled", True)])
            else:
                rule_count = len([k for k, v in profile.get("rules", {}).items() if v])
            item = QListWidgetItem(f"{profile.get('name', '未命名')} ({rule_count}条/{ref_count}只)")
            item.setData(Qt.UserRole, profile.get("id"))
            self.list_strategy_templates.addItem(item)
        if self.list_strategy_templates.count() > 0:
            self.list_strategy_templates.setCurrentRow(0)
            self._on_strategy_template_selected(0)

    def _send_strategy_push_test(self):
        self._on_strategy_config_changed()
        sender = getattr(self.win, "send_strategy_push_test", None)
        if callable(sender):
            sender()

    def _on_warning_changed(self, *_args):
        self.win.set_warning(self.chk_warning_visible.isChecked(), self.edit_warning_text.text())

    def _on_market_amount_changed(self, *_args):
        self.win.set_market_amount_visible(self.chk_market_amount_visible.isChecked())

    def _on_price_alert_badge_visible_changed(self, *_args):
        visible = self.sender().isChecked() if self.sender() is not None else self.chk_price_alert_badge_visible.isChecked()
        if self.chk_price_alert_badge_visible.isChecked() != visible:
            self.chk_price_alert_badge_visible.blockSignals(True)
            try:
                self.chk_price_alert_badge_visible.setChecked(visible)
            finally:
                self.chk_price_alert_badge_visible.blockSignals(False)
        setter = getattr(self.win, "set_price_alert_badge_visible", None)
        if callable(setter):
            setter(visible)
        else:
            self.win.price_alert_badge_visible = visible

    # —— 其它槽 —— #
    def _on_interval_changed(self, idx):
        seconds = self.cmb_interval.currentData()
        if isinstance(seconds,int): 
            self.win.set_refresh_interval(seconds)

    def _sync_data_source_enabled(self):
        custom = self.cmb_data_source_mode.currentData() == "custom"
        self.edit_data_url.setEnabled(custom)
        self.edit_data_headers.setEnabled(custom)

    def _on_data_source_changed(self, *_args):
        self._sync_data_source_enabled()
        headers_text = self.edit_data_headers.text().strip()
        headers = {}
        if headers_text:
            try:
                parsed = json.loads(headers_text)
                if isinstance(parsed, dict):
                    headers = {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                headers = {}
        self.win.set_data_source({
            "mode": self.cmb_data_source_mode.currentData() or "sina",
            "url_template": self.edit_data_url.text().strip(),
            "headers": headers,
            "fields": (getattr(self.win, "data_source", {}) or {}).get("fields", {}),
        })

    def _on_default_color_toggled(self, checked: bool):
        self.btn_fg.setEnabled(not checked)
        self.win.set_default_color(bool(checked))
    
    def _on_grid_toggled(self, checked: bool):
        self.win.set_grid_visible(bool(checked))

    def _on_header_toggled(self, checked: bool):
        self.win.set_header_visible(bool(checked))

    def _on_cb_changed(self, header: str, state: bool):
        self.win.set_flag(header, state)
        if header == "代码":
            self.cb_short_code.setEnabled(state)
        elif header == "名称":
            self.cmb_namelength.setEnabled(state)
    
    def _on_short_code_toggled(self, checked: bool):
        self.win.set_code_type(checked)

    def _on_name_length_changed(self, length: int):
        self.win.set_name_length(length)

    def _on_b1s1_display_changed(self, idx: int):
        try:
            val = self.cmb_b1s1_display.itemData(idx)
            if not val:
                return
            self.win.set_b1s1_display(val)
        except Exception:
            pass

    def _on_b1s1_toggled(self, state: bool):
        self.win.set_flag("买一", state)
        self.cmb_b1s1_display.setEnabled(state)

    def _apply_tab_size(self, index: int):
        size = self.tab_sizes.get(index, QSize(400, 400))
        if index in (0, 1, 2):
            self.setMinimumSize(size)
            self.setMaximumSize(16777215, 16777215)
            self.resize(size)
        else:
            self.setMinimumSize(size)
            self.setMaximumSize(size)
            self.resize(size)

    def pick_fg(self):
        c = QColorDialog.getColor(self.win.fg, self, "选择文字颜色")
        if c.isValid(): self.win.set_fg_color(c)
    def pick_bg(self):
        base = QColor(self.win.bg)
        base.setAlpha(255)
        c = QColorDialog.getColor(base, self, "选择背景颜色")
        if c.isValid(): self.win.set_bg_rgb_keep_alpha(c)
    def apply_bg_alpha(self, v): 
        self.lbl_bg_alpha.setText(f"{v}%")
        self.win.set_bg_alpha_percent(v)
    def apply_win_opacity(self, v): 
        self.lbl_win_opacity.setText(f"{v}%")
        self.win.set_window_opacity_percent(v)
    def _on_family_changed(self, fam: str): 
        self.win.set_font_family(fam)
    def apply_font_size(self, v):
        self.lbl_font.setText(f"{v} pt")
        self.win.set_font_size(v)  # 同步 K 线缩放
    def _on_line_changed(self, v: int): 
        self.lbl_line.setText(f"+{v} px")
        self.win.set_line_extra(v)
    def _on_hotkey_changed(self):
        new_hotkey = self.edit_hotkey.keySequence().toString()
        try:
            self.win.update_hotkey(new_hotkey)
        except Exception:
            pass

    def _on_icon_changed(self, idx: int):
        try:
            val = self.cmb_icon.itemData(idx)
            if not val:
                return
            if hasattr(self, 'app') and self.app is not None:
                try:
                    self.app.set_app_icon(val)
                    # persist immediately
                    try:
                        self.app.save_now()
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def _pick_custom_icon(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "选择图标文件", os.path.expanduser('~'), "图标文件 (*.ico);;All Files (*)")
            if path:
                # append or find existing custom entry
                idx = self.cmb_icon.findData(path)
                if idx < 0:
                    self.cmb_icon.addItem('自定义', userData=path)
                    idx = self.cmb_icon.count()-1
                self.cmb_icon.setCurrentIndex(idx)
                # trigger change handler will call app.set_app_icon
        except Exception:
            pass
