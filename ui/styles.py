"""Prism 设计系统 — Sigma 风格桌面应用

色彩与 QSS 生成器。
"""
# ============================================================
# 色彩 — Sigma 风格
# ============================================================
BG_PAGE = "#FAFAF7"
BG_SIDEBAR = "#F5F5F0"
BG_SURFACE = "#FFFFFF"
BG_HOVER = "#F0F0EB"
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
COLOR_ORANGE = "#D4A853"
COLOR_BLUE = "#6B8EB3"

# 语义化表面色：新增深色表面时在此登记，滚动条等派生颜色即自动适配
BG_TERMINAL = TEXT_PRIMARY

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

/* ---- 无边框窗口内容区（WA_TranslucentBackground 下取代 QMainWindow 背景） ---- */
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
#secondaryBtn:disabled {{ color: {TEXT_MUTED}; background: {BG_SURFACE}; border-color: {BORDER}; }}

#ghostBtn {{
    background: transparent;
    border: none;
    border-radius: 0px;
    color: {TEXT_MUTED};
    padding: 4px 10px;
}}
#ghostBtn:hover {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; }}

#dangerBtn {{
    background: transparent;
    border: 1px solid rgba(244,67,54,0.3);
    border-radius: 0px;
    color: {COLOR_RED};
    padding: 4px 13px;
    font-weight: 500;
}}
#dangerBtn:hover {{ background: rgba(244,67,54,0.06); }}

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

/* ---- 滚动区域（全局统一，消除各页面的重复内联样式） ---- */
QScrollArea {{ background: transparent; border: none; }}

/* ---- 自定义标题栏 ---- */
#titleBar {{ background: {BG_PAGE}; }}
"""
