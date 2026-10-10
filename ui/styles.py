"""Prism 设计系统 — Sigma 风格桌面应用

色彩、尺寸常量与 QSS 生成器；文末 STATUS_LABELS / STATUS_COLORS 为项目状态词表。
"""
# ============================================================
# 色彩 — Sigma 风格
# ============================================================
BG_PAGE = "#FAFAF7"
BG_SIDEBAR = "#F5F5F0"
BG_SURFACE = "#FFFFFF"
BG_HOVER = "#F0F0EB"
BG_PRESSED = "#E4E4DF"
BG_INPUT = "#F5F5F0"

ACCENT = "#C4A265"
ACCENT_HOVER = "#B8963E"

TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#555555"
TEXT_MUTED = "#999999"
TEXT_ON_DARK = "#FFFFFF"

BORDER = "#E8E8E5"
BORDER_LIGHT = "#F0F0ED"

COLOR_GREEN = "#6B8E6B"
COLOR_RED = "#C46B6B"
COLOR_RED_HOVER = "#B25C5C"
COLOR_RED_PRESSED = "#9E5252"
COLOR_ORANGE = "#D4A853"
COLOR_BLUE = "#6B8EB3"

# 失焦（窗口非激活）时的收敛色
TEXT_INACTIVE = "#AAAAA5"
BG_INACTIVE_CHECKED = "#EFEFEA"

# 语义化表面色：新增深色表面时在此登记，滚动条等派生颜色即自动适配
BG_TERMINAL = TEXT_PRIMARY

# 深色表面上的文字与语义色（结论横幅等，比浅色页面版亮一档）
DARK_TEXT = "#F5F5F2"
DARK_MUTED = "#8A8A86"
DARK_GOOD = "#9CC49C"
DARK_BAD = "#D98C8C"

# ============================================================
# 数据可视化色板 — 折线图 / 泳道图 / 雷达图统一取色
# 低饱和暖灰调，与 Sigma 底色同源；各色明度一致，并置无跳色感
# ============================================================
CHART_BLUE = "#64809B"      # 石灰蓝
CHART_ORANGE = "#C08A54"    # 陶土橙
CHART_GREEN = "#7D9B76"     # 鼠尾草绿
CHART_PURPLE = "#93799B"    # 灰紫
CHART_RED = "#B96A67"       # 砖红
CHART_TEAL = "#6E9696"      # 灰青
CHART_DARK = "#46465A"      # 深石灰（强调/介入类）
CHART_NEUTRAL = "#E3E3DD"   # 中性灰（维持/基线类，非类别色）

# ============================================================
# 尺寸
# ============================================================
RADIUS = 0
SIDEBAR_W = 200
HEADER_H = 48
BTN_H = 30

PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 24


# ============================================================
# 派生色工具：由背景色自动推导前景/把手颜色
# 未来接入多主题时只需替换上面的调色板常量，派生逻辑不变
# ============================================================

def _luminance(hex_color: str) -> float:
    """sRGB 感知亮度（0~1），用于判断背景深浅。"""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _scrollbar_qss(bg: str, scope: str = "") -> str:
    """生成滚动条 QSS：把手基色与透明度由背景亮度自动推导（深底浅条、浅底深条）。

    scope 为限定选择器（如 "#terminalLog"），空字符串表示全局。
    """
    dark_bg = _luminance(bg) < 0.5
    base = 255 if dark_bg else 0
    normal, hover, pressed = (0.28, 0.45, 0.58) if dark_bg else (0.16, 0.30, 0.42)
    p = f"{scope} " if scope else ""

    def rgba(opacity: float) -> str:
        return f"rgba({base}, {base}, {base}, {opacity})"

    return f"""
{p}QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
{p}QScrollBar::handle:vertical {{
    background: {rgba(normal)}; border-radius: 0px;
    min-height: 20px;
}}
{p}QScrollBar::handle:vertical:hover {{ background: {rgba(hover)}; }}
{p}QScrollBar::handle:vertical:pressed {{ background: {rgba(pressed)}; }}
{p}QScrollBar::add-line:vertical, {p}QScrollBar::sub-line:vertical {{ height: 0; }}
{p}QScrollBar::add-page:vertical, {p}QScrollBar::sub-page:vertical {{ background: transparent; }}
{p}QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
{p}QScrollBar::handle:horizontal {{
    background: {rgba(normal)}; border-radius: 0px;
    min-width: 20px;
}}
{p}QScrollBar::handle:horizontal:hover {{ background: {rgba(hover)}; }}
{p}QScrollBar::handle:horizontal:pressed {{ background: {rgba(pressed)}; }}
{p}QScrollBar::add-line:horizontal, {p}QScrollBar::sub-line:horizontal {{ width: 0; }}
{p}QScrollBar::add-page:horizontal, {p}QScrollBar::sub-page:horizontal {{ background: transparent; }}
"""


def stylesheet() -> str:
    return f"""
* {{ font-size: 13px; color: {TEXT_PRIMARY}; font-family: 'Space Grotesk', 'Noto Sans SC'; }}
QWidget {{ background: transparent; }}
QMainWindow {{ background: {BG_PAGE}; }}

/* ---- 无边框窗口内容区 ---- */
#windowBody {{ background: {BG_PAGE}; }}

/* ---- 侧边栏 ---- */
#sidebar {{
    background: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
    padding: 0;
}}
#sidebar QLabel#brand {{
    font-family: 'JetBrains Mono';
    font-size: 15px;
    font-weight: 800;
    color: {TEXT_PRIMARY};
    letter-spacing: 1px;
    padding: 12px 16px 8px 16px;
}}
#sidebar QPushButton {{
    background: transparent;
    border: none;
    border-radius: 0px;
    text-align: left;
    padding: 6px 12px;
    margin: 1px 8px;
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}
#sidebar QPushButton:hover {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
#sidebar QPushButton:checked {{
    /* 激活窗口的选中底色，比失焦态 BG_INACTIVE_CHECKED 略深一档以区分焦点层次 */
    background: #E8E8E8;
    color: {TEXT_PRIMARY};
    font-weight: 600;
}}

/* ---- 卡片 ---- */
#card {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 0px;
}}

/* ---- 基础组件类（ui/widgets.py 的语义组件，按类名匹配） ---- */
Title {{ color: {TEXT_PRIMARY}; }}
Caption {{ color: {TEXT_MUTED}; }}
Divider {{ background: {BORDER}; border: none; }}
PopupMenu {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; }}

/* ---- 按钮 ---- */
#primaryBtn {{
    background: {TEXT_PRIMARY};
    border: none;
    border-radius: 0px;
    color: {TEXT_ON_DARK};
    padding: 5px 14px;
    font-weight: 600;
}}
#primaryBtn:hover {{ background: {ACCENT}; }}
#primaryBtn:pressed {{ background: {ACCENT_HOVER}; }}
#primaryBtn:disabled {{ background: #CCC; color: #999; }}

#secondaryBtn {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 4px 13px;
    font-weight: 500;
}}
#secondaryBtn:hover {{ background: {BG_HOVER}; border-color: {TEXT_PRIMARY}; }}
#secondaryBtn:pressed {{ background: {BG_PRESSED}; }}
#secondaryBtn:disabled {{ color: {TEXT_MUTED}; background: {BG_SURFACE}; border-color: {BORDER}; }}

#ghostBtn {{
    background: transparent;
    border: none;
    border-radius: 0px;
    color: {TEXT_MUTED};
    padding: 4px 10px;
}}
#ghostBtn:hover {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; }}
#ghostBtn:pressed {{ background: {BG_PRESSED}; }}

#dangerBtn {{
    background: {COLOR_RED};
    border: none;
    border-radius: 0px;
    color: {TEXT_ON_DARK};
    padding: 5px 14px;
    font-weight: 600;
}}
#dangerBtn:hover {{ background: {COLOR_RED_HOVER}; }}
#dangerBtn:pressed {{ background: {COLOR_RED_PRESSED}; }}
#dangerBtn:disabled {{ background: rgba(196,107,107,0.15); color: rgba(196,107,107,0.5); }}

/* ---- 输入 ---- */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 5px 8px;
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {TEXT_PRIMARY};
}}

/* ---- 滑块 ---- */
QSlider::groove:horizontal {{
    background: {BORDER};
    height: 4px;
    border-radius: 0px;
}}
QSlider::handle:horizontal {{
    background: {TEXT_PRIMARY};
    width: 12px; height: 12px;
    margin: -4px 0;
    border-radius: 0px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QSlider::sub-page:horizontal {{ background: {TEXT_PRIMARY}; border-radius: 0px; }}

/* ---- 滚动条（把手颜色由背景亮度自动推导，见 _scrollbar_qss） ---- */
{_scrollbar_qss(BG_PAGE)}
{_scrollbar_qss(BG_TERMINAL, scope="#terminalLog")}

/* ---- 滚动区域（全局统一样式） ---- */
QScrollArea {{ background: transparent; border: none; }}
"""


# ============================================================
# 通用文本样式 — 跨页面复用的语义化文本档
# ============================================================

def hint_qss() -> str:
    """11px 弱化提示：图表注释、区块说明等辅助文字。"""
    return f"font-size:11px;color:{TEXT_MUTED};"


def small_text_qss(color: str) -> str:
    """12px 辅助文本：状态行、风险与建议条目等，颜色按语义传入。"""
    return f"font-size:12px;color:{color};"


def mono_value_qss(size: int, color: str, bold: bool = False) -> str:
    """等宽数字读数（JetBrains Mono）：指标数值、滑块读数、KPI 变化量。"""
    weight = "font-weight:700;" if bold else ""
    return f"font-family:'JetBrains Mono';font-size:{size}px;{weight}color:{color};"


# ============================================================
# 基础组件 QSS — ui/widgets.py 的组件级样式块
# ============================================================

def status_dot_qss(color: str) -> str:
    """状态圆点（● 字符着色）。"""
    return f"color: {color}; font-size: 10px;"


def segmented_qss() -> str:
    """分段按钮组：互斥单选，选中态反色。"""
    return f"""
    QPushButton {{
        background: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-radius: 0px;
        color: {TEXT_MUTED};
        padding: 3px 12px;
        font-size: 12px;
    }}
    QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; }}
    QPushButton:pressed {{ background: {BG_PRESSED}; }}
    QPushButton:checked {{
        background: {TEXT_PRIMARY};
        border: 1px solid {TEXT_PRIMARY};
        color: {TEXT_ON_DARK};
        font-weight: 600;
    }}
    """


def popup_item_qss() -> str:
    """弹出菜单条目按钮。"""
    return f"""
    QPushButton {{
        border: none;
        background: transparent;
        padding: 6px 16px;
        font-size: 12px;
        color: {TEXT_PRIMARY};
        text-align: left;
    }}
    QPushButton:hover {{ background: {TEXT_PRIMARY}; color: {TEXT_ON_DARK}; }}
    """


def dialog_button_qss(color: str = "") -> str:
    """确认弹窗通栏按钮；color 非空时叠加加粗与文字色（确定键）。"""
    qss = (
        f"QPushButton {{ border: none; background: transparent; font-size: 13px; padding: 10px 0; color: {TEXT_SECONDARY}; }}"
        f"QPushButton:hover {{ background: {BG_HOVER}; }}"
        f"QPushButton:pressed {{ background: {BG_PRESSED}; }}"
    )
    if color:
        qss += f"QPushButton {{ font-weight: 600; color: {color}; }}"
    return qss


def tip_popup_qss() -> str:
    """提示浮层（TipLabel 弹出的顶层 QLabel 无父控件，需自带完整样式）。"""
    return (
        f"background: {BG_SURFACE}; color: {TEXT_PRIMARY};"
        f"border: 1px solid {BORDER}; padding: 4px 8px; font-size: 11px;"
    )


def stepper_button_qss(inner_edge: str) -> str:
    """数值步进器加/减键；inner_edge 为靠输入框一侧（"left"/"right"），该侧边框并入输入框。"""
    return (
        f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};"
        f"border-{inner_edge}:none;font-size:14px;color:{TEXT_PRIMARY};}}"
        f"QPushButton:hover{{background:{BG_HOVER};}}"
        f"QPushButton:pressed{{background:{BG_PRESSED};}}"
        f"QPushButton:disabled{{background:{BG_SURFACE};color:rgba(26,26,26,0.3);}}"
    )


def stepper_input_qss() -> str:
    """数值步进器输入框：两侧边框由加减键提供。"""
    return (
        f"QLineEdit{{background:{BG_INPUT};border:1px solid {BORDER};"
        f"border-left:none;border-right:none;font-family:'JetBrains Mono';font-size:13px;color:{TEXT_PRIMARY};}}"
        f"QLineEdit:focus{{border:1px solid {TEXT_PRIMARY};}}"
    )


# ============================================================
# 标题栏与主窗口
# ============================================================

def title_brand_qss(color: str) -> str:
    """标题栏品牌标签；颜色随窗口焦点切换。"""
    return (
        f"font-family:'JetBrains Mono';font-size:12px;"
        f"font-weight:700;color:{color};letter-spacing:1px;"
    )


def sidebar_inactive_qss() -> str:
    """窗口失焦时的侧栏收敛态：选中底色减淡、文字变灰。"""
    return (
        f"#sidebar QPushButton{{color:{TEXT_INACTIVE};}}"
        f"#sidebar QPushButton:checked{{background:{BG_INACTIVE_CHECKED};color:{TEXT_MUTED};}}"
        f"#sidebar QLabel#brand{{color:{TEXT_MUTED};}}"
    )


# ============================================================
# 工作区（ui/process_page.py）— 顶栏与日志终端
# ============================================================

def workspace_bar_qss() -> str:
    """工作区顶栏：深色实底。"""
    return f"background:{TEXT_PRIMARY};"


def workspace_step_tag_qss() -> str:
    """顶栏步骤序号标签（STEP 01）：品牌金底白字等宽体。"""
    return (
        f"background:{ACCENT};color:{TEXT_ON_DARK};padding:2px 8px;"
        "font-family:'JetBrains Mono';font-size:10px;font-weight:700;"
    )


def workspace_step_name_qss() -> str:
    """顶栏步骤名称。"""
    return f"font-size:13px;font-weight:700;color:{TEXT_ON_DARK};"


def terminal_qss() -> str:
    """日志终端控制台（#terminalLog，配色与全局滚动条作用域同源）。"""
    return (
        "QPlainTextEdit{"
        f"background:{BG_TERMINAL};color:#AAA;"
        "font-family:'JetBrains Mono','Noto Sans SC';font-size:11px;"
        "border:none;padding:0px;"
        "}"
    )


# ============================================================
# 仿真页（ui/simulation_page.py）
# ============================================================

def simulation_log_qss() -> str:
    """仿真日志区：浅底输入风格的只读日志框。"""
    return f"QTextEdit{{background:{BG_INPUT};border:1px solid {BORDER};font-size:12px;padding:0px;}}"


# ============================================================
# 项目页（ui/projects_page.py）
# ============================================================

def project_card_qss(clickable: bool) -> str:
    """项目卡片按钮；回收站卡片不可点击（clickable=False），无悬停描边。"""
    qss = f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
    if clickable:
        qss += f"QPushButton:hover {{ border-color: {TEXT_PRIMARY}; }}"
    return qss


def project_status_qss(color: str) -> str:
    """卡片上的项目状态文字，颜色取 STATUS_COLORS。"""
    return f"font-size: 11px; font-weight: 600; color: {color};"


def project_name_qss() -> str:
    """卡片上的项目名称。"""
    return f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};"


def project_empty_qss() -> str:
    """列表空态提示（居中大字）。"""
    return f"color: {TEXT_MUTED}; font-size: 14px; padding: 40px;"


# ============================================================
# 行为体配置页（ui/persona_page.py）
# ============================================================

def role_badge_qss() -> str:
    """行为体角色徽章：细线描边小标签。"""
    return f"font-size:11px;color:{TEXT_MUTED};border:1px solid {BORDER};padding:1px 8px;"


# ============================================================
# 结果页（ui/result_page.py）— 深色结论横幅与明细表
# ============================================================

def report_banner_qss() -> str:
    """结论横幅：深色实底（#reportBanner）。"""
    return f"#reportBanner{{background:{TEXT_PRIMARY};}}"


def banner_title_qss() -> str:
    """横幅标题。"""
    return f"color:{DARK_TEXT};"


def banner_meta_qss() -> str:
    """横幅项目名与日期行。"""
    return f"font-size:12px;color:{DARK_MUTED};"


def banner_summary_qss() -> str:
    """横幅演化概述。"""
    return "font-size:12px;color:#AAAAA5;"


def verdict_qss(color: str) -> str:
    """结论文案，颜色由推荐等级映射（ok/warn/risk）。"""
    return f"color:{color};"


def kpi_value_qss() -> str:
    """横幅 KPI 数值。"""
    return mono_value_qss(18, DARK_TEXT, bold=True)


def kpi_name_qss() -> str:
    """横幅 KPI 名称。"""
    return f"font-size:10px;color:{DARK_MUTED};"


def kpi_delta_qss(color: str) -> str:
    """横幅 KPI 变化量，颜色按方向语义传入。"""
    return mono_value_qss(10, color)


def table_header_qss() -> str:
    """明细数据表头。"""
    return (
        f"font-size:11px;color:{TEXT_MUTED};padding:2px 8px;"
        f"border-bottom:1px solid {BORDER};"
    )


def table_cell_qss() -> str:
    """明细数据单元格（等宽数字，右对齐由控件设置）。"""
    return (
        "font-family:'JetBrains Mono';font-size:12px;"
        f"color:{TEXT_PRIMARY};padding:2px 8px;"
        f"border-bottom:1px solid {BORDER_LIGHT};"
    )


# ============================================================
# 泳道图（ui/charts.py）
# ============================================================

def swimlane_header_qss(has_event: bool) -> str:
    """周期表头：含关键事件的周期标红。"""
    return f"color:{COLOR_RED if has_event else TEXT_MUTED};"


def swimlane_name_qss() -> str:
    """行为体名列。"""
    return f"font-size:11px;color:{TEXT_SECONDARY};"


def swimlane_cell_qss(color: str = "") -> str:
    """行动色块；color 为空表示该周期无行动（透明空格）。"""
    return f"background:{color};" if color else "background:transparent;"


def legend_dot_qss(color: str) -> str:
    """图例色块符号（■ 字符着色）。"""
    return f"color:{color};font-size:10px;"


def legend_text_qss() -> str:
    """图例文字。"""
    return f"font-size:10px;color:{TEXT_MUTED};"


# ============================================================
# 设置页（ui/settings_page.py）
# ============================================================

def settings_status_qss(color: str) -> str:
    """设置页状态行文字色：进行中用普通文字色，成功/失败用语义色。"""
    return f"color:{color};"


# ============================================================
# 项目状态词表（状态 → 中文标签 / 语义色）
# ============================================================
STATUS_LABELS = {
    "draft": "草稿",
    "running": "运行中",
    "interrupted": "已中断",
    "completed": "已完成",
}
STATUS_COLORS = {
    "draft": COLOR_ORANGE,
    "running": COLOR_BLUE,
    "interrupted": COLOR_RED,
    "completed": COLOR_GREEN,
}
