"""Prism 设计系统 — Linear.app 风格全暗色主题

核心特征（来自 Linear 设计语言分析）：
  1. 全暗色 — 不纯黑，微冷调中性灰 (#08090A → #0F1115 → #16171A)
  2. 亚像素低透明度白色边框 — rgba(255,255,255,0.06)，不是硬色值线条
  3. 紧凑密度 — 13px 基础字号，28px 行高，6px 圆角
  4. 强调色克制 — 大部分 UI 灰阶，accent 只用于焦点/主按钮/选中
  5. 即时 hover — 无过渡动画
  6. 光谱渐变仅用于品牌点睛（Logo / Hero），不铺满 UI
"""

# ============================================================
# 色彩 — Linear dark palette
# ============================================================

# 背景层级（暗→亮，2-3% 明度步进）
BG_SIDEBAR = "#08090A"       # 最暗 — 侧边栏
BG_CANVAS = "#0F1115"        # 主内容区
BG_SURFACE = "#16171A"       # 卡片/面板
BG_SURFACE_HOVER = "#1C1D21"  # hover 态

# 强调色 — Linear signature periwinkle
ACCENT = "#5E6AD2"
ACCENT_RGB = "94, 106, 210"
ACCENT_HOVER = "#6E7AE6"
ACCENT_PRESSED = "#4D59B8"
ACCENT_MUTED = f"rgba({ACCENT_RGB}, 0.12)"    # 选中行
ACCENT_SUBTLE = f"rgba({ACCENT_RGB}, 0.06)"   # hover 微染

# 品牌渐变 — 仅用于 Logo / Hero CTA
BRAND_GRADIENT_START = "#5E6AD2"
BRAND_GRADIENT_END = "#7C5CFC"

# 光谱色 — 仅图表用
SPECTRUM_INDIGO = "#5B5FEF"
SPECTRUM_VIOLET = "#7C3AED"
SPECTRUM_CYAN = "#06B6D4"
SPECTRUM_GREEN = "#10B981"

# 文字层级
TEXT_PRIMARY = "#E6E6E8"
TEXT_SECONDARY = "#B4B8BF"
TEXT_TERTIARY = "#8A8F98"
TEXT_QUATERNARY = "#62666D"
TEXT_ON_ACCENT = "#FFFFFF"

# 亚像素边框 — Linear 签名
BORDER_SUBTLE = "rgba(255, 255, 255, 0.06)"
BORDER_DEFAULT = "rgba(255, 255, 255, 0.09)"
BORDER_STRONG = "rgba(255, 255, 255, 0.14)"
BORDER_ACCENT = f"rgba({ACCENT_RGB}, 0.50)"

# 状态色（仅用于小圆点/pill，不大面积填充）
COLOR_POSITIVE = "#4CB782"
COLOR_NEGATIVE = "#EB5757"
COLOR_WARNING = "#F2C94C"

# ============================================================
# 圆角 — concentric
# ============================================================
RADIUS_CARD = 8
RADIUS_BUTTON = 6
RADIUS_INPUT = 6
RADIUS_NAV = 6
RADIUS_BADGE = 4

# ============================================================
# 布局
# ============================================================
SIDEBAR_WIDTH = 240

SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24
SPACING_XXL = 32

# ============================================================
# QSS
# ============================================================

def generate_stylesheet() -> str:
    return f"""
/* ===== 全局 ===== */
* {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}

QWidget {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
}}

QMainWindow {{
    background-color: {BG_CANVAS};
}}

/* 内容区统一背景 — 所有页面继承 */
QStackedWidget {{
    background-color: {BG_CANVAS};
}}
QStackedWidget > QWidget {{
    background-color: {BG_CANVAS};
}}
QScrollArea {{
    background-color: {BG_CANVAS};
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {BG_CANVAS};
}}

/* ===== 侧边栏 — 扁平最暗层 ===== */
#sidebar {{
    background-color: {BG_SIDEBAR};
    border: none;
    border-right: 1px solid {BORDER_SUBTLE};
}}

#sidebarAppName {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}

/* 导航项 */
QPushButton.nav-btn {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_NAV}px;
    text-align: left;
    padding: 7px 12px;
    font-size: 13px;
    font-weight: 400;
    color: {TEXT_SECONDARY};
}}
QPushButton.nav-btn:hover {{
    background-color: rgba(255, 255, 255, 0.05);
    color: {TEXT_PRIMARY};
}}
QPushButton.nav-btn:checked {{
    background-color: rgba(255, 255, 255, 0.06);
    color: {TEXT_PRIMARY};
    font-weight: 500;
}}

/* ===== 滚动条 — 极简自动淡化 ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.10);
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.18);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 0.10);
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(255, 255, 255, 0.18);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ===== 卡片 — 提升面层，亚像素边框 ===== */
QFrame#prismCard {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_CARD}px;
}}

/* ===== 按钮 — 紧凑 28px 高 ===== */
/* 主按钮 — accent 实色（Linear 风格，不渐变） */
QPushButton#primaryBtn {{
    background-color: {ACCENT};
    border: none;
    border-radius: {RADIUS_BUTTON}px;
    color: {TEXT_ON_ACCENT};
    padding: 5px 14px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#primaryBtn:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryBtn:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QPushButton#primaryBtn:disabled {{
    background-color: rgba(255, 255, 255, 0.06);
    color: {TEXT_QUATERNARY};
}}

/* 次按钮 — 微透白底 + 亚像素边框 */
QPushButton#secondaryBtn {{
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_BUTTON}px;
    color: {TEXT_PRIMARY};
    padding: 4px 13px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#secondaryBtn:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid {BORDER_STRONG};
}}
QPushButton#secondaryBtn:pressed {{
    background-color: rgba(255, 255, 255, 0.10);
}}

/* 幽灵按钮 */
QPushButton#ghostBtn {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_BUTTON}px;
    color: {TEXT_TERTIARY};
    padding: 4px 10px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#ghostBtn:hover {{
    background-color: rgba(255, 255, 255, 0.04);
    color: {TEXT_PRIMARY};
}}

/* 危险按钮 */
QPushButton#dangerBtn {{
    background: transparent;
    border: 1px solid rgba(235, 87, 87, 0.30);
    border-radius: {RADIUS_BUTTON}px;
    color: {COLOR_NEGATIVE};
    padding: 4px 13px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#dangerBtn:hover {{
    background: rgba(235, 87, 87, 0.10);
    border: 1px solid rgba(235, 87, 87, 0.50);
}}

/* ===== 输入框 ===== */
QLineEdit, QPlainTextEdit, QTextEdit,
QSpinBox, QDoubleSpinBox {{
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_INPUT}px;
    padding: 5px 10px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    selection-background-color: rgba({ACCENT_RGB}, 0.30);
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {BORDER_ACCENT};
}}
QLineEdit::placeholder, QPlainTextEdit::placeholder {{
    color: {TEXT_QUATERNARY};
}}

/* ===== 下拉框 ===== */
QComboBox {{
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_INPUT}px;
    padding: 5px 10px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QComboBox:focus {{
    border: 1px solid {BORDER_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_BADGE}px;
    selection-background-color: {ACCENT_MUTED};
    selection-color: {TEXT_PRIMARY};
    outline: none;
    padding: 4px;
    color: {TEXT_PRIMARY};
}}

/* ===== 滑块 ===== */
QSlider::groove:horizontal {{
    background: rgba(255, 255, 255, 0.08);
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT_PRIMARY};
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
}}
QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

/* ===== 进度条 ===== */
QProgressBar {{
    background-color: rgba(255, 255, 255, 0.06);
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* ===== 分组框 ===== */
QGroupBox {{
    font-weight: 600;
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_CARD}px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TEXT_PRIMARY};
}}

/* ===== 列表 ===== */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
    color: {TEXT_PRIMARY};
}}
QListWidget::item {{
    border-radius: {RADIUS_NAV}px;
    padding: 6px 10px;
    color: {TEXT_SECONDARY};
}}
QListWidget::item:hover {{
    background-color: rgba(255, 255, 255, 0.04);
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {TEXT_PRIMARY};
}}

/* ===== 表格 ===== */
QTableWidget {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_CARD}px;
    gridline-color: {BORDER_SUBTLE};
    color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    padding: 8px 12px;
    font-weight: 600;
    color: {TEXT_TERTIARY};
}}

/* ===== 标签页 ===== */
QTabWidget::pane {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_CARD}px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    color: {TEXT_TERTIARY};
    font-size: 13px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
}}

/* ===== 工具提示 ===== */
QToolTip {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_BADGE}px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ===== 复选框 ===== */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {TEXT_PRIMARY};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.04);
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ===== 状态标签 ===== */
QLabel#statusPositive {{ color: {COLOR_POSITIVE}; font-weight: 600; }}
QLabel#statusNegative {{ color: {COLOR_NEGATIVE}; font-weight: 600; }}
QLabel#statusWarning {{ color: {COLOR_WARNING}; font-weight: 600; }}
"""
