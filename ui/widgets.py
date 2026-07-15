"""Prism 组件 — 简洁桌面组件"""
from PySide6.QtWidgets import (
    QFrame, QPushButton, QLineEdit, QLabel, QVBoxLayout, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.styles import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT,
    BORDER, BTN_H, PAD_LG, PAD_MD,
)


class Card(QFrame):
    """白底 + 细线边框卡片"""
    def __init__(self, parent=None, padding=PAD_LG):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ly = QVBoxLayout(self)
        self._ly.setContentsMargins(padding, padding, padding, padding)
        self._ly.setSpacing(PAD_MD)

    def add(self, w): self._ly.addWidget(w)
    def add_layout(self, l): self._ly.addLayout(l)
    def add_stretch(self, s=1): self._ly.addStretch(s)


class PrimaryBtn(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("primaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BTN_H)


class SecondaryBtn(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("secondaryBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BTN_H)


class GhostBtn(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("ghostBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BTN_H)


class DangerBtn(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("dangerBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BTN_H)


class Input(QLineEdit):
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setFixedHeight(BTN_H)


class Title(QLabel):
    def __init__(self, text="", size=18, parent=None):
        super().__init__(text, parent)
        f = QFont()
        f.setPointSize(size)
        f.setBold(True)
        self.setFont(f)
        self.setStyleSheet(f"color: {TEXT_PRIMARY};")


class Subtitle(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        f = QFont()
        f.setPointSize(13)
        self.setFont(f)
        self.setStyleSheet(f"color: {TEXT_SECONDARY};")


class Caption(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        f = QFont()
        f.setPointSize(11)
        self.setFont(f)
        self.setStyleSheet(f"color: {TEXT_MUTED};")


class MonoLabel(QLabel):
    """等宽字体标签 — 用于数据/编号"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        f = QFont("JetBrains Mono")
        f.setPointSize(12)
        f.setBold(True)
        self.setFont(f)
        self.setStyleSheet(f"color: {TEXT_PRIMARY};")


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {BORDER}; border: none;")


class StatusDot(QLabel):
    def __init__(self, color=ACCENT, parent=None):
        super().__init__("●", parent)
        self.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.setFixedSize(12, 12)
