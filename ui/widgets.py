"""Prism 组件库 — Linear.app 风格

紧凑密度 + 亚像素边框 + 克制强调色。
按钮 28-30px 高，卡片 #16171A 面层，无重投影。
"""

from PySide6.QtWidgets import (
    QFrame,
    QPushButton,
    QLineEdit,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from prism.ui.styles import (
    BG_SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_QUATERNARY,
    BORDER_SUBTLE,
    BORDER_DEFAULT,
    RADIUS_CARD,
    RADIUS_BUTTON,
    SPACING_LG,
    SPACING_MD,
)


# ============================================================
# 卡片 — 提升面层 + 亚像素边框，无投影
# ============================================================

class PrismCard(QFrame):
    """内容卡片 — #16171A 背景 + rgba(255,255,255,0.06) 边框"""

    def __init__(self, parent=None, padding: int = SPACING_LG):
        super().__init__(parent)
        self.setObjectName("prismCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(SPACING_MD)

    def addWidget(self, widget):
        self._layout.addWidget(widget)

    def addLayout(self, layout):
        self._layout.addLayout(layout)

    def addStretch(self, stretch: int = 1):
        self._layout.addStretch(stretch)


# ============================================================
# 按钮 — 紧凑 28px
# ============================================================

class PrismPrimaryButton(QPushButton):
    """主按钮 — accent 实色"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("primaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)


class PrismSecondaryButton(QPushButton):
    """次按钮 — 微透白底"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("secondaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)


class PrismGhostButton(QPushButton):
    """幽灵按钮 — 无背景"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("ghostBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)


class PrismDangerButton(QPushButton):
    """危险按钮"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("dangerBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)


# ============================================================
# 输入框
# ============================================================

class PrismLineEdit(QLineEdit):
    """输入框 — 微透背景 + accent 焦点边框"""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setFixedHeight(30)


# ============================================================
# 标签 — Linear 文字层级
# ============================================================

class PrismLabel(QLabel):
    """通用标签"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)


class LargeTitle(QLabel):
    """大标题 — 28px / 700"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_PRIMARY};")


class DisplayTitle(QLabel):
    """超大标题 — Hero 用"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(32)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_PRIMARY};")


class SectionTitle(QLabel):
    """区块标题 — 17px / 600"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_PRIMARY};")


class SubtitleLabel(QLabel):
    """副标题 — 15px / 灰色"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        font = QFont()
        font.setPointSize(15)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_TERTIARY};")


class BodyLabel(QLabel):
    """正文 — 13px / 次要色"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        font = QFont()
        font.setPointSize(13)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_SECONDARY};")


class CaptionLabel(QLabel):
    """说明文字 — 11px / 四级灰"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        font = QFont()
        font.setPointSize(11)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_QUATERNARY};")


class SectionLabel(QLabel):
    """分组标签 — 11px uppercase"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text.upper(), parent)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(f"color: {TEXT_QUATERNARY}; letter-spacing: 0.6px;")


# ============================================================
# 分隔线 — 亚像素
# ============================================================

class PrismDivider(QFrame):
    """水平分隔线 — rgba(255,255,255,0.06)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumHeight(1)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: {BORDER_SUBTLE}; border: none;")


# ============================================================
# 状态圆点 — Linear 风格小色点
# ============================================================

class StatusDot(QLabel):
    """状态圆点 — 8px 圆点 + 颜色"""

    def __init__(self, color: str = "#4CB782", parent=None):
        super().__init__("●", parent)
        self.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.setFixedSize(14, 14)


# ============================================================
# 占位页面
# ============================================================

class PlaceholderPage(QFrame):
    """占位页面 — 居中标题 + 描述"""

    def __init__(self, title: str = "", description: str = "", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 80, 80, 80)
        layout.setAlignment(Qt.AlignCenter)

        title_label = QLabel(title)
        t_font = QFont()
        t_font.setPointSize(28)
        t_font.setBold(True)
        title_label.setFont(t_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")

        desc_label = QLabel(description)
        d_font = QFont()
        d_font.setPointSize(15)
        desc_label.setFont(d_font)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setMaximumWidth(520)
        desc_label.setStyleSheet(f"color: {TEXT_TERTIARY};")

        layout.addStretch(2)
        layout.addWidget(title_label)
        layout.addSpacing(16)
        layout.addWidget(desc_label)
        layout.addStretch(3)
