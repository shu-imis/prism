"""自定义标题栏 — 平台自适配 macOS / Windows，支持环境变量 PRISM_TITLEBAR_STYLE 强制切换"""
import os
import sys

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QWidget,
)
from PySide6.QtGui import QCursor, QMouseEvent, QPainter, QPainterPath, QPen, QColor

from ui.styles import (
    BG_PAGE, BG_SIDEBAR, BORDER, SIDEBAR_W, TEXT_PRIMARY, TEXT_MUTED, TEXT_ON_DARK,
    title_brand_qss,
)

TITLE_BAR_H = 36

# macOS 红绿灯：单颗直径与组内间距，按钮组宽度由这两个常量推算
MAC_BTN_SIZE = 12
MAC_BTN_SPACING = 8

# 平台检测：环境变量 PRISM_TITLEBAR_STYLE 可强制指定 "macos" / "windows"
_forced = os.environ.get("PRISM_TITLEBAR_STYLE", "").lower()
if _forced in ("macos", "windows"):
    IS_MAC = _forced == "macos"
else:
    IS_MAC = sys.platform == "darwin"

# 系统外观复刻色（macOS 红绿灯 / Windows 10 窗口按钮），独立于应用调色板
MAC_CLOSE_COLOR = "#FF5F57"
MAC_MIN_COLOR = "#FFBD2E"
MAC_MAX_COLOR = "#28CA41"
MAC_INACTIVE_COLOR = "#D0D0D0"      # 失焦时的灰点
WIN_HOVER_COLOR = "#E5E5E5"
WIN_PRESSED_COLOR = "#DBDBDB"
WIN_CLOSE_COLOR = "#E81123"
WIN_CLOSE_PRESSED_COLOR = "#BF1700"
WIN_INACTIVE_GLYPH_COLOR = "#BBBBBB"


class _MacTraffic(QPushButton):
    """macOS 红绿灯按钮 — 悬停态由标题栏按胶囊触发区整组驱动"""

    def __init__(self, color, symbol, parent=None):
        super().__init__(parent)
        self._color = color
        self._symbol = symbol  # "close" | "min" | "max"
        self._group_hover = False
        self._active = True
        self.setFixedSize(MAC_BTN_SIZE, MAC_BTN_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)  # 窗口按钮不进 Tab 序列

    def set_group_hover(self, on: bool):
        if self._group_hover != on:
            self._group_hover = on
            self.update()

    def set_active(self, active: bool):
        if self._active != active:
            self._active = active
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 悬停时按钮「唤醒」为激活色，其余界面保持失焦灰
        fill = QColor(self._color if (self._active or self._group_hover) else MAC_INACTIVE_COLOR)
        if self.isDown():
            fill = fill.darker(120)  # 按压加深 20%
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(QRectF(0.5, 0.5, 11, 11))  # 圆心严格在 (6, 6)
        if self._group_hover:
            p.setPen(QPen(QColor(0, 0, 0, 130), 1.25))
            c = 6.0
            if self._symbol == "close":
                p.drawLine(QPointF(c - 2.4, c - 2.4), QPointF(c + 2.4, c + 2.4))
                p.drawLine(QPointF(c + 2.4, c - 2.4), QPointF(c - 2.4, c + 2.4))
            elif self._symbol == "min":
                p.drawLine(QPointF(c - 2.4, c), QPointF(c + 2.4, c))
            else:
                p.drawLine(QPointF(c - 2.4, c), QPointF(c + 2.4, c))
                p.drawLine(QPointF(c, c - 2.4), QPointF(c, c + 2.4))
        p.end()


class _WinButton(QPushButton):
    """Windows 风格窗口按钮 — 用 QPainter 绘制符号"""

    def __init__(self, kind, signal, parent=None):
        super().__init__(parent)
        self._kind = kind       # "min" | "max" | "close"
        self._hover = False
        self._active = True

        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)  # 窗口按钮不进 Tab 序列
        self.clicked.connect(signal.emit)

    def set_active(self, active):
        if self._active != active:
            self._active = active
            self.update()

    def set_hovered(self, on: bool):
        if self._hover != on:
            self._hover = on
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # 背景（悬停/按下色值对齐 Windows 10 原生）
        if self._kind == "close" and (self._hover or self.isDown()):
            p.fillRect(self.rect(), QColor(WIN_CLOSE_PRESSED_COLOR) if self.isDown() else QColor(WIN_CLOSE_COLOR))
        elif self._hover or self.isDown():
            p.fillRect(self.rect(), QColor(WIN_PRESSED_COLOR) if self.isDown() else QColor(WIN_HOVER_COLOR))

        # 符号：悬停/按下「唤醒」为激活色
        if self._hover and self._kind == "close":
            pen_color = QColor(TEXT_ON_DARK)
        elif self._active or self._hover or self.isDown():
            pen_color = QColor(TEXT_MUTED)
        else:
            pen_color = QColor(WIN_INACTIVE_GLYPH_COLOR)
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
            # 边距清零：12px 左边距在 left 容器内设置，此处不叠加布局默认边距
            layout.setContentsMargins(0, 0, 0, 0)
            self._build_macos(layout)
        else:
            layout.setContentsMargins(10, 0, 2, 0)
            self._build_windows(layout)

        # 悬停态由光标轮询统一驱动：系统不向失焦应用投递悬停事件；
        # 红绿灯触发区是包裹三颗圆点的胶囊，按光标位置判定而非控件边界
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(33)
        self._poll_timer.timeout.connect(self._poll_hover)
        self._poll_timer.start()

    def _poll_hover(self):
        # 模态弹窗在前时，背景窗口不响应悬停
        if QApplication.activeModalWidget() is not None:
            self._apply_hover(None)
            return
        # 按住鼠标期间（拖拽中）冻结悬停，松开后由下一轮按光标位置校正
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        self._apply_hover(self.childAt(self.mapFromGlobal(QCursor.pos())))

    def _apply_hover(self, child):
        """按光标位置驱动悬停态；child 为 None 时全部清除。"""
        if IS_MAC:
            on = child is not None and self._mac_capsule.contains(
                self._mac_area.mapFromGlobal(QCursor.pos())
            )
            for btn in self._mac_buttons:
                btn.set_group_hover(on)
        else:
            for btn in self._win_buttons:
                btn.set_hovered(child is btn)

    def paintEvent(self, event):
        """左侧条带与侧边栏同色、分隔线贯穿标题栏，让侧栏视觉上直通窗口顶部。"""
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG_PAGE))
        p.fillRect(QRect(0, 0, SIDEBAR_W, self.height()), QColor(BG_SIDEBAR))
        p.setPen(QColor(BORDER))
        p.drawLine(SIDEBAR_W, 0, SIDEBAR_W, self.height())
        p.end()

    def set_active(self, active: bool):
        """窗口焦点变化时更新标题栏外观。"""
        if IS_MAC:
            for btn in self._mac_buttons:
                btn.set_active(active)
        else:
            for btn in self._win_buttons:
                btn.set_active(active)
        c = TEXT_PRIMARY if active else TEXT_MUTED
        self._brand_label.setStyleSheet(title_brand_qss(c))

    # --- macOS：左侧红绿灯 ---

    def _build_macos(self, layout):
        close_btn = self._mac_traffic(MAC_CLOSE_COLOR, "close", self.closed)
        min_btn = self._mac_traffic(MAC_MIN_COLOR, "min", self.minimized)
        max_btn = self._mac_traffic(MAC_MAX_COLOR, "max", self.maximized)

        # 按钮组打包固定宽度
        area_w = MAC_BTN_SIZE * 3 + MAC_BTN_SPACING * 2
        btn_area = QWidget()
        bl = QHBoxLayout(btn_area)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(MAC_BTN_SPACING)
        bl.addWidget(close_btn)
        bl.addWidget(min_btn)
        bl.addWidget(max_btn)
        btn_area.setFixedWidth(area_w)

        # 悬停判定区：刚好包裹三颗圆点的胶囊（圆角取圆点半径）
        self._mac_area = btn_area
        self._mac_capsule = QPainterPath()
        self._mac_capsule.addRoundedRect(
            QRectF(0, 0, area_w, MAC_BTN_SIZE), MAC_BTN_SIZE / 2, MAC_BTN_SIZE / 2
        )

        # 左侧为侧栏延伸区（与 paintEvent 的色带同宽），红绿灯落在其上
        left = QWidget()
        left.setFixedWidth(SIDEBAR_W)
        ll = QHBoxLayout(left)
        ll.setContentsMargins(12, 0, 0, 0)
        ll.addWidget(btn_area, 0, Qt.AlignVCenter)
        ll.addStretch()

        self._mac_buttons = [close_btn, min_btn, max_btn]

        title = QLabel("PRISM")
        title.setStyleSheet(title_brand_qss(TEXT_PRIMARY))
        title.setAlignment(Qt.AlignCenter)

        layout.addWidget(left)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()
        self._brand_label = title

    def _mac_traffic(self, color, symbol, signal):
        btn = _MacTraffic(color, symbol)
        btn.clicked.connect(signal.emit)
        return btn

    # --- Windows：右侧 QPainter 按钮 ---

    def _build_windows(self, layout):
        brand = QLabel("PRISM")
        brand.setStyleSheet(title_brand_qss(TEXT_PRIMARY))
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
        btn_w = 46 * 3
        btn_area.setFixedWidth(btn_w)

        # 左侧让位宽度 = 侧栏延伸区 + 按钮组宽度，使标题恰好以内容区为参照居中
        spacer = QWidget()
        spacer.setFixedWidth(SIDEBAR_W + btn_w)

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
