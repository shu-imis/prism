"""滚动交互组件。

两个 Qt 默认行为的修正：
- SmoothScrollArea：触控板滚轮按像素 1:1 驱动（Qt 默认按行步进）；
- 链式文本控件：滚轮事件在自身滚到头后交还外层（Qt 默认无条件吞掉）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit, QScrollArea, QTextEdit


class SmoothScrollArea(QScrollArea):
    """像素级滚动的滚动区：触控板双轴跟手，鼠标滚轮回退默认行步进。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

    def wheelEvent(self, event):
        pixel = event.pixelDelta()
        if not pixel.isNull():
            if pixel.y():
                bar = self.verticalScrollBar()
                bar.setValue(bar.value() - pixel.y())
            if pixel.x():
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() - pixel.x())
            event.accept()
            return
        super().wheelEvent(event)


def _at_scroll_end(widget, delta: int) -> bool:
    """控件在指定滚动方向上是否已无余地（含内容不足以滚动的情形）。"""
    bar = widget.verticalScrollBar()
    if bar.maximum() == bar.minimum():
        return True
    if delta > 0 and bar.value() <= bar.minimum():
        return True
    return delta < 0 and bar.value() >= bar.maximum()


class _WheelChain:
    """滚轮链式传递：自身滚到头后忽略事件，交还外层滚动容器。

    Qt Widgets 的文本控件只响应 angleDelta 行步进；触控板 pixelDelta
    在此按像素直接驱动，与 SmoothScrollArea 的跟手口径一致。
    """

    def wheelEvent(self, event):
        pixel = event.pixelDelta().y()
        if pixel:
            if _at_scroll_end(self, pixel):
                event.ignore()
                return
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - pixel)
            event.accept()
            return
        if _at_scroll_end(self, event.angleDelta().y()):
            event.ignore()
            return
        super().wheelEvent(event)


class ChainingTextEdit(_WheelChain, QTextEdit):
    """滚到头的 QTextEdit 把滚轮事件交还外层。"""


class ChainingPlainTextEdit(_WheelChain, QPlainTextEdit):
    """滚到头的 QPlainTextEdit 把滚轮事件交还外层。"""
