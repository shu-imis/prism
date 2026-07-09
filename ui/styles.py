"""Prism 设计系统 — 桌面应用

MiroFish 视觉语言：
  - 白色背景 + 黑色文字 + 橙色点缀
  - 细线边框、小圆角
  - 等宽字体用于数据/标签
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

SPECTRUM_INDIGO = "#5B5FEF"
SPECTRUM_VIOLET = "#7C3AED"
SPECTRUM_CYAN = "#06B6D4"
SPECTRUM_GREEN = "#10B981"

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


def stylesheet() -> str:
    return f"""
* {{ font-size: 13px; color: {TEXT_PRIMARY}; font-family: 'Space Grotesk', 'Noto Sans SC'; }}
QWidget {{ background: transparent; }}
QMainWindow {{ background: {BG_PAGE}; }}

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
#secondaryBtn:hover {{ background: {BG_HOVER}; }}

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
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 5px 8px;
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {TEXT_PRIMARY};
}}
QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 5px 8px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    selection-background: {BG_HOVER};
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

/* ---- 进度条 ---- */
QProgressBar {{
    background: {BORDER};
    border: none;
    border-radius: 0px;
    height: 4px;
}}
QProgressBar::chunk {{ background: {TEXT_PRIMARY}; border-radius: 0px; }}

/* ---- 列表 ---- */
QListWidget {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 0px;
    outline: none;
    padding: 2px;
}}
QListWidget::item {{
    border-radius: 0px;
    padding: 5px 8px;
}}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{ background: #E8E8E8; }}

/* ---- 滚动条 ---- */
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: #CCC; border-radius: 0px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: #AAA; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 6px; }}
QScrollBar::handle:horizontal {{ background: #CCC; border-radius: 0px; min-width: 20px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---- 标签页 ---- */
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 0px; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    color: {TEXT_MUTED};
}}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}
QTabBar::tab:selected {{ color: {TEXT_PRIMARY}; border-bottom-color: {TEXT_PRIMARY}; }}

/* ---- 分组框 ---- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 0px;
    margin-top: 8px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}

/* ---- 表格 ---- */
QTableWidget {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 0px;
    gridline-color: {BORDER_LIGHT};
}}
QHeaderView::section {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
    font-weight: 600;
    color: {TEXT_MUTED};
}}

/* ---- 复选框 ---- */
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 0px;
    background: {BG_SURFACE};
}}
QCheckBox::indicator:checked {{ background: {TEXT_PRIMARY}; border-color: {TEXT_PRIMARY}; }}
"""
