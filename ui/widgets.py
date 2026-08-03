"""Prism 组件 — 简洁桌面组件"""
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QPushButton, QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy, QWidget,
)
from PySide6.QtCore import Qt, QEvent, QObject, QPoint, QRectF, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter
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


class PopupMenu(QFrame):
    """自绘弹出菜单 — 替代 QMenu，避免 macOS 原生 NSMenu 渲染导致样式不一致。

    用法：menu = PopupMenu(parent); menu.add_action("删除", cb); menu.popup(global_pos)
    Qt.Popup 语义：点击菜单外区域自动关闭（与系统菜单一致），关闭即销毁。
    """

    _ITEM_QSS = f"""
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

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"PopupMenu {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; }}")
        self._ly = QVBoxLayout(self)
        self._ly.setContentsMargins(4, 4, 4, 4)
        self._ly.setSpacing(0)

    def add_action(self, text: str, callback) -> None:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._ITEM_QSS)
        btn.clicked.connect(lambda checked=False, cb=callback: (self.close(), cb()))
        self._ly.addWidget(btn)

    def popup(self, global_pos) -> None:
        self.move(global_pos)
        self.show()


class _TipDismissFilter(QObject):
    """全局解散过滤器：提示浮层打开期间，点击或滚动任意位置即关闭。

    常驻安装、永不拦截事件（始终返回 False），浮层关闭时是完全的空转，
    因此不影响应用内任何控件的交互。
    """

    def eventFilter(self, watched, event):
        owner = TipLabel._owner
        if owner is not None:
            t = event.type()
            # 点击宿主自身不在这里处理，交给宿主的 mousePressEvent 做开关切换
            if t == QEvent.Wheel or (t == QEvent.MouseButtonPress and watched is not owner):
                TipLabel.hide_tip()
        return False


class TipLabel(QLabel):
    """点击查看提示的 QLabel — 替代原生 QToolTip，跨平台外观一致。

    点击显示浮层；再次点击自身切换关闭；点击/滚动其他任意位置、切页、
    宿主销毁时关闭。全应用同时最多一个浮层（类级管理）。
    """

    _TIP_QSS = (
        f"background: {BG_SURFACE}; color: {TEXT_PRIMARY};"
        f"border: 1px solid {BORDER}; padding: 4px 8px; font-size: 11px;"
    )
    _popup = None  # 当前打开的浮层（QLabel）
    _owner = None  # 浮层所属的 TipLabel

    def __init__(self, text="", tip="", parent=None):
        super().__init__(text, parent)
        self._tip = tip
        if tip:
            self.setCursor(Qt.PointingHandCursor)
        # 注意：必须连接 lambda 而非自身绑定方法——Qt 销毁对象时会先清理
        # "接收者是自身"的连接，self.destroyed.connect(self.method) 不会触发
        self.destroyed.connect(lambda *args, s=self: TipLabel._on_owner_gone(s))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._tip:
            # accept 阻止事件向父级传播：传播会再次经过全局过滤器，
            # 被误判为"点击浮层外部"而把刚打开的浮层立即关掉
            event.accept()
            if TipLabel._owner is self:
                TipLabel.hide_tip()  # 再点一次 = 关闭
            else:
                TipLabel.show_tip(self)
            return
        super().mousePressEvent(event)

    def event(self, event):
        # 切页/父容器隐藏时（QStackedWidget 只隐藏不销毁）关闭所属浮层
        if event.type() in (QEvent.Hide, QEvent.HideToParent) and TipLabel._owner is self:
            TipLabel.hide_tip()
        return super().event(event)

    @classmethod
    def _on_owner_gone(cls, owner) -> None:
        if cls._owner is owner:
            cls.hide_tip()

    @classmethod
    def show_tip(cls, owner) -> None:
        cls.hide_tip()
        popup = QLabel(owner._tip, None, Qt.ToolTip | Qt.FramelessWindowHint)
        popup.setAttribute(Qt.WA_DeleteOnClose)
        popup.setStyleSheet(cls._TIP_QSS)
        popup.setWordWrap(True)

        # 约束在光标所在屏幕的可用区域内：超宽先限宽换行，右/下溢出则回收到屏幕内
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area:
            max_w = max(200, area.width() - 24)
            if popup.sizeHint().width() > max_w:
                popup.setFixedWidth(max_w)
            popup.adjustSize()
            size = popup.size()
            pos = cursor_pos + QPoint(12, 16)
            if pos.x() + size.width() > area.right() + 1:
                pos.setX(max(area.left(), area.right() - size.width() + 1))
            if pos.y() + size.height() > area.bottom() + 1:
                pos.setY(cursor_pos.y() - size.height() - 4)  # 下方放不下时翻转到光标上方
        else:
            pos = cursor_pos + QPoint(12, 16)
        popup.move(pos)
        popup.show()
        # 浮层被外部销毁（如应用退出）时清空引用；按身份比对，
        # 避免"关旧开新"后旧浮层的延迟销毁误清新浮层的引用
        popup.destroyed.connect(lambda *args, p=popup: cls._on_popup_gone(p))
        cls._popup = popup
        cls._owner = owner
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(_TIP_DISMISS_FILTER)

    @classmethod
    def hide_tip(cls) -> None:
        popup = cls._popup
        cls._popup = None
        cls._owner = None
        if popup is not None:
            try:
                popup.close()  # WA_DeleteOnClose：关闭即销毁
            except RuntimeError:
                pass  # 浮层已随应用退出被销毁

    @classmethod
    def _on_popup_gone(cls, popup) -> None:
        if cls._popup is popup:
            cls._popup = None
            cls._owner = None


_TIP_DISMISS_FILTER = _TipDismissFilter()


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



