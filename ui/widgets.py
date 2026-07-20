"""Prism 组件 — 简洁桌面组件"""
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QPushButton, QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy, QWidget,
)
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, TEXT_ON_DARK, ACCENT, BG_INPUT, BG_SURFACE, BG_HOVER,
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


class SegmentedControl(QWidget):
    """分段按钮组 — 互斥单选，替代下拉框。"""

    valueChanged = Signal(str)

    _QSS = f"""
    QPushButton {{
        background: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-radius: 0px;
        color: {TEXT_MUTED};
        padding: 3px 12px;
        font-size: 12px;
    }}
    QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; }}
    QPushButton:checked {{
        background: {TEXT_PRIMARY};
        border: 1px solid {TEXT_PRIMARY};
        color: {TEXT_ON_DARK};
        font-weight: 600;
    }}
    """

    def __init__(self, options: list[tuple[str, str]], parent=None):
        """options: [(value, label), ...]，同一时刻仅一个按钮处于选中态。"""
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._values: dict[QPushButton, str] = {}
        for value, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(BTN_H - 4)
            btn.setStyleSheet(self._QSS)
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._values[btn] = value
            btn.clicked.connect(lambda checked, val=value: self.valueChanged.emit(val))

    def value(self) -> str:
        checked = self._group.checkedButton()
        return self._values.get(checked, "") if checked else ""

    def set_value(self, value: str) -> None:
        for btn, v in self._values.items():
            btn.setChecked(v == value)


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


class Caption(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        f = QFont()
        f.setPointSize(11)
        self.setFont(f)
        self.setStyleSheet(f"color: {TEXT_MUTED};")


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


class NumberInput(QWidget):
    """带加减按钮的数值输入框 — 左右布局"""
    def __init__(self, value=0, min_val=0, max_val=100, step=1, parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._step = step

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._minus = QPushButton("−")
        self._minus.setFixedSize(BTN_H, BTN_H)
        self._minus.setCursor(Qt.PointingHandCursor)
        self._minus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-right:none;font-size:14px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._minus.clicked.connect(self._decrease)
        layout.addWidget(self._minus)

        self._input = QLineEdit(str(value))
        self._input.setFixedHeight(BTN_H)
        self._input.setAlignment(Qt.AlignCenter)
        self._input.setStyleSheet(
            f"QLineEdit{{background:{BG_INPUT};border:1px solid {BORDER};border-left:none;border-right:none;font-family:'JetBrains Mono';font-size:13px;color:{TEXT_PRIMARY};}}"
            f"QLineEdit:focus{{border:1px solid {TEXT_PRIMARY};}}"
        )
        self._input.editingFinished.connect(self._validate_input)
        layout.addWidget(self._input)

        self._plus = QPushButton("＋")
        self._plus.setFixedSize(BTN_H, BTN_H)
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-left:none;font-size:14px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._plus.clicked.connect(self._increase)
        layout.addWidget(self._plus)

    def _increase(self):
        try:
            val = int(self._input.text())
            val = min(val + self._step, self._max)
            self._input.setText(str(val))
        except ValueError:
            pass

    def _decrease(self):
        try:
            val = int(self._input.text())
            val = max(val - self._step, self._min)
            self._input.setText(str(val))
        except ValueError:
            pass

    def _validate_input(self):
        try:
            val = int(self._input.text())
            val = max(self._min, min(val, self._max))
            self._input.setText(str(val))
        except ValueError:
            self._input.setText(str(self._min))

    def value(self):
        try:
            return int(self._input.text())
        except ValueError:
            return self._min

    def setValue(self, val):
        val = max(self._min, min(val, self._max))
        self._input.setText(str(val))

    def setRange(self, min_val, max_val):
        self._min = min_val
        self._max = max_val

    def setSingleStep(self, step):
        self._step = step


class ProgressBar(QWidget):
    """自定义进度条 — QPainter 绘制，macOS 上显示一致"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setValue(self, value: int):
        self._value = max(0, min(100, int(value)))
        self.update()

    def setFormat(self, _fmt: str):
        pass  # 始终显示百分比

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        # 轨道
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BORDER))
        painter.drawRect(0, 0, w, h)

        # 填充
        if self._value > 0:
            fill_w = int(w * self._value / 100)
            painter.setBrush(QColor(TEXT_PRIMARY))
            painter.drawRect(0, 0, fill_w, h)

        # 文字 — 填充过半时切换为白色
        text = f"{self._value}%"
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(TEXT_ON_DARK if self._value > 45 else TEXT_PRIMARY))
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, text)
        painter.end()



class DecimalInput(QWidget):
    """带加减按钮的小数输入框 — 左右布局"""
    def __init__(self, value=0.0, min_val=0.0, max_val=1.0, step=0.05, decimals=2, parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._step = step
        self._decimals = decimals

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._minus = QPushButton("−")
        self._minus.setFixedSize(BTN_H, BTN_H)
        self._minus.setCursor(Qt.PointingHandCursor)
        self._minus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-right:none;font-size:14px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._minus.clicked.connect(self._decrease)
        layout.addWidget(self._minus)

        self._input = QLineEdit(f"{value:.{decimals}f}")
        self._input.setFixedHeight(BTN_H)
        self._input.setAlignment(Qt.AlignCenter)
        self._input.setStyleSheet(
            f"QLineEdit{{background:{BG_INPUT};border:1px solid {BORDER};border-left:none;border-right:none;font-family:'JetBrains Mono';font-size:13px;color:{TEXT_PRIMARY};}}"
            f"QLineEdit:focus{{border:1px solid {TEXT_PRIMARY};}}"
        )
        self._input.editingFinished.connect(self._validate_input)
        layout.addWidget(self._input)

        self._plus = QPushButton("＋")
        self._plus.setFixedSize(BTN_H, BTN_H)
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-left:none;font-size:14px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._plus.clicked.connect(self._increase)
        layout.addWidget(self._plus)

    def _increase(self):
        try:
            val = float(self._input.text())
            val = round(min(val + self._step, self._max), self._decimals)
            self._input.setText(f"{val:.{self._decimals}f}")
        except ValueError:
            pass

    def _decrease(self):
        try:
            val = float(self._input.text())
            val = round(max(val - self._step, self._min), self._decimals)
            self._input.setText(f"{val:.{self._decimals}f}")
        except ValueError:
            pass

    def _validate_input(self):
        try:
            val = float(self._input.text())
            val = round(max(self._min, min(val, self._max)), self._decimals)
            self._input.setText(f"{val:.{self._decimals}f}")
        except ValueError:
            self._input.setText(f"{self._min:.{self._decimals}f}")

    def value(self):
        try:
            return float(self._input.text())
        except ValueError:
            return self._min

    def setValue(self, val):
        val = round(max(self._min, min(val, self._max)), self._decimals)
        self._input.setText(f"{val:.{self._decimals}f}")

    def setRange(self, min_val, max_val):
        self._min = min_val
        self._max = max_val

    def setSingleStep(self, step):
        self._step = step



