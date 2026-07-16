"""自定义标题栏 — 平台自适配 macOS / Windows，支持环境变量 PRISM_TITLEBAR_STYLE 强制切换"""
import os
import sys

from PySide6.QtCore import Qt, QPoint, QRect, Signal, QSize
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QWidget,
)
from PySide6.QtGui import QMouseEvent, QPainter, QPen, QColor

from ui.styles import TEXT_PRIMARY, TEXT_MUTED

TITLE_BAR_H = 36

# 平台检测：环境变量 PRISM_TITLEBAR_STYLE 可强制指定 "macos" / "windows"
_forced = os.environ.get("PRISM_TITLEBAR_STYLE", "").lower()
if _forced in ("macos", "windows"):
    IS_MAC = _forced == "macos"
else:
    IS_MAC = sys.platform == "darwin"


class _WinButton(QPushButton):
    """Windows 风格窗口按钮 — 用 QPainter 绘制符号"""

    def __init__(self, kind, signal, parent=None):
        super().__init__(parent)
        self._kind = kind       # "min" | "max" | "close"
        self._hover = False

        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(signal.emit)
        self._active = True

    def set_active(self, active):
        self._active = active
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # 背景
        if self._kind == "close" and self._hover:
            p.fillRect(self.rect(), QColor("#E81123"))
        elif self._hover:
            p.fillRect(self.rect(), QColor(0, 0, 0, 8))

        # 符号
        pen_color = QColor("#999") if self._active else QColor("#BBB")
        if self._hover and self._kind == "close":
            pen_color = QColor("#FFF")
        p.setPen(QPen(pen_color, 1.2))

        cx, cy = w // 2, h // 2

        if self._kind == "min":
            p.drawLine(cx - 4, cy, cx + 4, cy)

        elif self._kind == "max":
            p.drawRect(QRect(cx - 4, cy - 4, 8, 8))

        elif self._kind == "close":
            p.drawLine(cx - 4, cy - 4, cx + 4, cy + 4)
            p.drawLine(cx + 4, cy - 4, cx - 4, cy + 4)

        p.end()


class TitleBar(QWidget):
    """无边框窗口的自定义标题栏"""

    minimized = Signal()
    maximized = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._drag_pos = QPoint()

        self.setFixedHeight(TITLE_BAR_H)
        self.setObjectName("titleBar")
        self._mac_buttons = []
        self._win_buttons = []
        self._brand_label = None

        layout = QHBoxLayout(self)
        layout.setSpacing(0)

        if IS_MAC:
            layout.setContentsMargins(12, 0, 0, 0)
            self._build_macos(layout)
        else:
            layout.setContentsMargins(10, 0, 2, 0)
            self._build_windows(layout)

    def set_active(self, active: bool):
        """窗口焦点变化时更新标题栏外观"""
        if IS_MAC:
            for btn, color in self._mac_buttons:
                c = color if active else "#D0D0D0"
                btn.setStyleSheet(
                    "QPushButton{background:" + c + ";border:none;border-radius:6px;}"
                )
            c = TEXT_PRIMARY if active else TEXT_MUTED
            self._brand_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:12px;"
                "font-weight:700;color:" + c + ";letter-spacing:1px;"
            )
        else:
            c = TEXT_PRIMARY if active else TEXT_MUTED
            self._brand_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:12px;"
                "font-weight:700;color:" + c + ";letter-spacing:1px;"
            )
            for btn in self._win_buttons:
                btn.set_active(active)

    # --- macOS：左侧红绿灯 ---

    def _build_macos(self, layout):
        btn_size = QSize(12, 12)
        close_btn = self._mac_traffic("#FF5F57", btn_size, self.closed)
        min_btn = self._mac_traffic("#FFBD2E", btn_size, self.minimized)
        max_btn = self._mac_traffic("#28CA41", btn_size, self.maximized)

        # 按钮组打包固定宽度
        btn_area = QWidget()
        bl = QHBoxLayout(btn_area)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        bl.addWidget(close_btn)
        bl.addWidget(min_btn)
        bl.addWidget(max_btn)
        btn_area.setFixedWidth(12 + 8 + 12 + 8 + 12)

        # 右侧对称占位
        spacer = QWidget()
        spacer.setFixedWidth(12 + 8 + 12 + 8 + 12)

        self._mac_buttons = [
            (close_btn, "#FF5F57"),
            (min_btn, "#FFBD2E"),
            (max_btn, "#28CA41"),
        ]

        title = QLabel("PRISM")
        title.setStyleSheet(
            "font-family:'JetBrains Mono';font-size:12px;"
            "font-weight:700;color:" + TEXT_PRIMARY + ";letter-spacing:1px;"
        )
        title.setAlignment(Qt.AlignCenter)

        layout.addWidget(btn_area)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(spacer)
        self._brand_label = title

    def _mac_traffic(self, color, size, signal):
        btn = QPushButton()
        btn.setFixedSize(size)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{background:" + color + ";border:none;border-radius:6px;}"
        )
        btn.clicked.connect(signal.emit)
        return btn

    # --- Windows：右侧 QPainter 按钮 ---

    def _build_windows(self, layout):
        brand = QLabel("PRISM")
        brand.setStyleSheet(
            "font-family:'JetBrains Mono';font-size:12px;"
            "font-weight:700;color:" + TEXT_PRIMARY + ";letter-spacing:1px;"
        )
        brand.setAlignment(Qt.AlignCenter)
        self._brand_label = brand

        min_btn = _WinButton("min", self.minimized)
        max_btn = _WinButton("max", self.maximized)
        close_btn = _WinButton("close", self.closed)
        self._win_buttons = [min_btn, max_btn, close_btn]

        btn_area = QWidget()
        bl = QHBoxLayout(btn_area)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(min_btn)
        bl.addWidget(max_btn)
        bl.addWidget(close_btn)
        btn_area.setFixedWidth(46 * 3)

        spacer = QWidget()
        spacer.setFixedWidth(46 * 3)

        layout.addWidget(spacer)
        layout.addStretch()
        layout.addWidget(brand)
        layout.addStretch()
        layout.addWidget(btn_area)

    # --- 拖拽移动 ---

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.window().move(self.window().pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.maximized.emit()
