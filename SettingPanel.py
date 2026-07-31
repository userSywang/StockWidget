import json
import os, re
from functools import partial

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QPushButton, QSlider,
    QGroupBox, QLabel, QColorDialog, QComboBox, QAbstractItemView,
    QCheckBox, QListWidget, QListWidgetItem, QKeySequenceEdit, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QDoubleSpinBox
)
from WidgetPanel import FloatLabel
from StockLogic import (
    DEFAULT_WARNING_TEXT,
    default_alert_rule,
    default_price_alert,
    normalize_alert_rule,
    normalize_alert_rules,
    normalize_alert_target,
    normalize_code_or_none,
    normalize_price_alert,
    normalize_price_alerts,
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
            0: QSize(360, 340),
            1: QSize(440, 420),
            2: QSize(520, 240),
            3: QSize(500, 520),
            4: QSize(360, 350),
            5: QSize(300, 220),
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
        self.tree_codes.setFixedWidth(210)
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
        for b in (self.btn_add, self.btn_add_group, self.btn_del, self.btn_up, self.btn_dn):
            btn_col.addWidget(b)
        btn_col.addStretch(1)

        lay_codes.addWidget(self.tree_codes, 1)
        lay_codes.addLayout(btn_col)
        code_settings.addWidget(g_codes)

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
        gl_flags.addWidget(g_flag_other, 2, 0)

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

        self.tabs.addTab(tab_source, "数据源")

        # ---- 第三页：提醒 ----
        tab_alert = QWidget()
        alert_settings = QVBoxLayout(tab_alert)

        g_alert = QGroupBox("联动提醒")
        g_alert.setContentsMargins(3,12,3,6)
        lay_alert = QHBoxLayout(g_alert)
        lay_alert.setSpacing(6)

        left_alert = QVBoxLayout()
        self.list_alerts = QListWidget()
        self.list_alerts.setFixedWidth(130)
        left_alert.addWidget(self.list_alerts)
        alert_btns = QHBoxLayout()
        self.btn_alert_add = QPushButton("添加")
        self.btn_alert_del = QPushButton("删除")
        self.btn_alert_add.setFixedWidth(58)
        self.btn_alert_del.setFixedWidth(58)
        alert_btns.addWidget(self.btn_alert_add)
        alert_btns.addWidget(self.btn_alert_del)
        left_alert.addLayout(alert_btns)
        lay_alert.addLayout(left_alert)

        form_alert = QGridLayout()
        form_alert.setHorizontalSpacing(6)
        form_alert.setVerticalSpacing(6)
        self.chk_alert_enabled = QCheckBox("启用")
        self.edit_alert_name = QLineEdit()
        self.cmb_alert_mode = QComboBox()
        self.cmb_alert_mode.addItem("触发时显示", userData="on_trigger")
        self.cmb_alert_mode.addItem("常显状态", userData="always")
        self.list_alert_targets = QListWidget()
        self.list_alert_targets.setFixedHeight(96)
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

        form_alert.addWidget(self.chk_alert_enabled, 0, 0)
        form_alert.addWidget(QLabel("名称："), 0, 1)
        form_alert.addWidget(self.edit_alert_name, 0, 2, 1, 3)
        form_alert.addWidget(QLabel("显示："), 1, 0)
        form_alert.addWidget(self.cmb_alert_mode, 1, 1, 1, 2)
        form_alert.addWidget(QLabel("标的："), 2, 0)
        form_alert.addWidget(self.list_alert_targets, 2, 1, 1, 4)
        target_btns = QHBoxLayout()
        target_btns.addWidget(self.btn_target_add)
        target_btns.addWidget(self.btn_target_del)
        target_btns.addStretch(1)
        form_alert.addLayout(target_btns, 3, 1, 1, 4)
        form_alert.addWidget(QLabel("代码："), 4, 0)
        form_alert.addWidget(self.edit_target_code, 4, 1)
        form_alert.addWidget(self.cmb_target_op, 4, 2)
        form_alert.addWidget(self.spin_target_pct, 4, 3)
        form_alert.addWidget(self.chk_target_volume, 4, 4)
        form_alert.addWidget(QLabel("消息："), 5, 0)
        form_alert.addWidget(self.edit_alert_message, 5, 1, 1, 4)
        lay_alert.addLayout(form_alert, 1)
        alert_settings.addWidget(g_alert)

        g_price_alert = QGroupBox("价格提醒")
        g_price_alert.setContentsMargins(3,12,3,6)
        lay_price_alert = QHBoxLayout(g_price_alert)
        lay_price_alert.setSpacing(6)

        left_price = QVBoxLayout()
        self.list_price_alerts = QListWidget()
        self.list_price_alerts.setFixedWidth(130)
        left_price.addWidget(self.list_price_alerts)
        price_btns = QHBoxLayout()
        self.btn_price_alert_add = QPushButton("添加")
        self.btn_price_alert_del = QPushButton("删除")
        self.btn_price_alert_add.setFixedWidth(58)
        self.btn_price_alert_del.setFixedWidth(58)
        price_btns.addWidget(self.btn_price_alert_add)
        price_btns.addWidget(self.btn_price_alert_del)
        left_price.addLayout(price_btns)
        lay_price_alert.addLayout(left_price)

        form_price = QGridLayout()
        form_price.setHorizontalSpacing(6)
        form_price.setVerticalSpacing(6)
        self.chk_price_alert_enabled = QCheckBox("启用")
        self.edit_price_alert_code = QLineEdit()
        self.cmb_price_alert_direction = QComboBox()
        self.cmb_price_alert_direction.addItem("高于/等于", userData="above")
        self.cmb_price_alert_direction.addItem("低于/等于", userData="below")
        self.spin_price_alert_price = QDoubleSpinBox()
        self.spin_price_alert_price.setRange(0.0, 99999.999)
        self.spin_price_alert_price.setDecimals(3)
        self.edit_price_alert_message = QLineEdit()

        form_price.addWidget(self.chk_price_alert_enabled, 0, 0)
        form_price.addWidget(QLabel("代码："), 0, 1)
        form_price.addWidget(self.edit_price_alert_code, 0, 2)
        form_price.addWidget(self.cmb_price_alert_direction, 0, 3)
        form_price.addWidget(self.spin_price_alert_price, 0, 4)
        form_price.addWidget(QLabel("提示："), 1, 0)
        form_price.addWidget(self.edit_price_alert_message, 1, 1, 1, 4)
        lay_price_alert.addLayout(form_price, 1)
        alert_settings.addWidget(g_price_alert)

        g_warning = QGroupBox("警醒标语")
        g_warning.setContentsMargins(3,12,3,6)
        lay_warning = QGridLayout(g_warning)
        self.chk_warning_visible = QCheckBox("显示")
        self.chk_warning_visible.setChecked(bool(getattr(self.win, "warning_visible", False)))
        self.edit_warning_text = QLineEdit(getattr(self.win, "warning_text", DEFAULT_WARNING_TEXT))
        lay_warning.addWidget(self.chk_warning_visible, 0, 0)
        lay_warning.addWidget(self.edit_warning_text, 0, 1)
        alert_settings.addWidget(g_warning)

        g_market = QGroupBox("市场概览")
        g_market.setContentsMargins(3,12,3,6)
        lay_market = QGridLayout(g_market)
        self.chk_market_amount_visible = QCheckBox("显示沪深成交额估算")
        self.chk_market_amount_visible.setChecked(bool(getattr(self.win, "market_amount_visible", False)))
        lay_market.addWidget(self.chk_market_amount_visible, 0, 0)
        alert_settings.addWidget(g_market)

        self._loading_alert_editor = False
        self._loading_target_editor = False
        self._loading_price_alert_editor = False
        self._load_alert_list()
        self._load_price_alert_list()
        self.tabs.addTab(tab_alert, "提醒")

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

        # ---- 连接 ----
        # 连接：代码列表
        self.tree_codes.itemChanged.connect(self._on_codes_changed)
        self.btn_add.clicked.connect(self._add_code)
        self.btn_add_group.clicked.connect(self._add_group)
        self.btn_del.clicked.connect(self._del_code)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_dn.clicked.connect(self._move_down)
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
        self.chk_price_alert_enabled.toggled.connect(self._on_price_alert_editor_changed)
        self.edit_price_alert_code.editingFinished.connect(self._on_price_alert_editor_changed)
        self.cmb_price_alert_direction.currentIndexChanged.connect(self._on_price_alert_editor_changed)
        self.spin_price_alert_price.valueChanged.connect(self._on_price_alert_editor_changed)
        self.edit_price_alert_message.editingFinished.connect(self._on_price_alert_editor_changed)
        self.chk_warning_visible.toggled.connect(self._on_warning_changed)
        self.edit_warning_text.editingFinished.connect(self._on_warning_changed)
        self.chk_market_amount_visible.toggled.connect(self._on_market_amount_changed)
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

    def _make_group_item(self, name: str):
        item = QTreeWidgetItem([str(name or "分组")])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setData(0, Qt.UserRole, "group")
        return item

    def _make_code_item(self, code: str, checked: bool, pending: bool = False):
        item = QTreeWidgetItem([code])
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
        for group in getattr(self.win, "groups", []) or [{"name": "默认", "codes": self.win.codes}]:
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
                    norm = normalize_code_or_none(child.text(0))
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
                    if child.text(0) != norm:
                        child.setText(0, norm)
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
        direction = "高于" if alert.get("direction") == "above" else "低于"
        suffix = "" if alert.get("enabled", True) else "（停用）"
        return f"{alert.get('code', '')} {direction} {float(alert.get('price', 0.0)):.3f}{suffix}"

    def _load_price_alert_list(self, current_row=0):
        self.list_price_alerts.blockSignals(True)
        self.list_price_alerts.clear()
        self._price_alerts = normalize_price_alerts(getattr(self.win, "price_alerts", []))
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
            self.chk_price_alert_enabled.setChecked(bool(alert.get("enabled", True)))
            self.edit_price_alert_code.setText(alert.get("code", "sh000001"))
            idx = self.cmb_price_alert_direction.findData(alert.get("direction", "above"))
            self.cmb_price_alert_direction.setCurrentIndex(idx if idx >= 0 else 0)
            self.spin_price_alert_price.setValue(float(alert.get("price", 0.0)))
            self.edit_price_alert_message.setText(alert.get("message", ""))
        finally:
            self._loading_price_alert_editor = False

    def _collect_price_alert_from_editor(self):
        return normalize_price_alert({
            "enabled": self.chk_price_alert_enabled.isChecked(),
            "code": self.edit_price_alert_code.text(),
            "direction": self.cmb_price_alert_direction.currentData(),
            "price": self.spin_price_alert_price.value(),
            "message": self.edit_price_alert_message.text(),
        })

    def _on_price_alert_editor_changed(self, *_args):
        if getattr(self, "_loading_price_alert_editor", False):
            return
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
        alerts = list(getattr(self, "_price_alerts", normalize_price_alerts([])))
        alert = default_price_alert()
        if getattr(self.win, "codes", None):
            alert["code"] = self.win.codes[0]
        alerts.append(alert)
        self.win.set_price_alerts(alerts)
        self._load_price_alert_list(len(alerts) - 1)

    def _del_price_alert(self):
        row = self._current_price_alert_row()
        if row < 0:
            return
        alerts = list(getattr(self, "_price_alerts", []))
        if 0 <= row < len(alerts):
            alerts.pop(row)
        self.win.set_price_alerts(alerts)
        self._load_price_alert_list(max(0, row - 1))

    def _on_warning_changed(self, *_args):
        self.win.set_warning(self.chk_warning_visible.isChecked(), self.edit_warning_text.text())

    def _on_market_amount_changed(self, *_args):
        self.win.set_market_amount_visible(self.chk_market_amount_visible.isChecked())

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
        self.setFixedSize(size)

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
