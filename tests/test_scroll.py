"""滚动交互测试：像素滚动、滚轮链式传递与 Tab 焦点导航。"""
from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from tests.qt_helpers import QtDbTestCase, app as _app
from ui.scroll import ChainingTextEdit, SmoothScrollArea
from ui.widgets import LogView


def _wheel(pixel_y: int = 0, angle_y: int = 0, pixel_x: int = 0) -> QWheelEvent:
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(pixel_x, pixel_y),
        QPoint(0, angle_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


class _ScrollHost(QWidget):
    """外层 SmoothScrollArea 包内嵌文本框的最小场景（编辑框 600px 使外层可滚）。"""

    def __init__(self, lines: int):
        super().__init__()
        self.setFixedSize(300, 200)
        self.edit = ChainingTextEdit()
        self.edit.setFixedHeight(600)
        self.edit.setPlainText("\n".join(f"第 {i} 行" for i in range(lines)))
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)
        self.scroll = SmoothScrollArea()
        self.scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)


class SmoothScrollAreaTests(QtDbTestCase):
    def test_pixel_delta_scrolls_one_to_one(self) -> None:
        """触控板 pixelDelta 按像素 1:1 驱动滚动条。"""
        host = self.track(_ScrollHost(lines=200))
        host.show()
        bar = host.scroll.verticalScrollBar()
        before = bar.value()
        host.scroll.wheelEvent(_wheel(pixel_y=-30))
        self.assertEqual(bar.value() - before, 30)

    def test_angle_delta_falls_back_to_default_stepping(self) -> None:
        """无 pixelDelta（鼠标滚轮）时回退默认行步进，滚动仍然发生。"""
        host = self.track(_ScrollHost(lines=200))
        host.show()
        bar = host.scroll.verticalScrollBar()
        host.scroll.wheelEvent(_wheel(angle_y=-120))
        self.assertGreater(bar.value(), 0)

    def test_pixel_delta_scrolls_horizontally(self) -> None:
        """触控板横向 pixelDelta 按像素 1:1 驱动横向滚动条。"""
        host = self.track(_ScrollHost(lines=200))
        host.edit.setFixedWidth(800)
        host.show()
        bar = host.scroll.horizontalScrollBar()
        host.scroll.wheelEvent(_wheel(pixel_x=-25))
        self.assertEqual(bar.value(), 25)


class WheelChainTests(QtDbTestCase):
    def test_inner_at_end_ignores_wheel(self) -> None:
        """内嵌文本框滚到底后，滚轮事件被忽略（Qt 据此交还外层）。"""
        host = self.track(_ScrollHost(lines=200))
        host.show()
        inner_bar = host.edit.verticalScrollBar()
        inner_bar.setValue(inner_bar.maximum())
        event = _wheel(pixel_y=-40)
        host.edit.wheelEvent(event)
        self.assertFalse(event.isAccepted())

    def test_inner_scrollable_consumes_wheel(self) -> None:
        """内嵌文本框自身可滚时：事件被接受且内层滚动条移动。"""
        host = self.track(_ScrollHost(lines=200))
        host.show()
        inner_bar = host.edit.verticalScrollBar()
        inner_bar.setValue(0)
        event = _wheel(pixel_y=-40)
        host.edit.wheelEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertGreater(inner_bar.value(), 0)


class TabNavigationTests(QtDbTestCase):
    def test_tab_leaves_multiline_editor(self) -> None:
        """多行文本控件让位 Tab：焦点从文本框走向单行输入。"""
        host = self.track(QWidget())
        layout = QVBoxLayout(host)
        text_edit = ChainingTextEdit()
        line = QLineEdit()
        for w in (text_edit, line):
            layout.addWidget(w)
        host.resize(300, 300)
        host.show()
        _app().processEvents()

        text_edit.setFocus()
        _app().processEvents()
        self.assertTrue(text_edit.hasFocus())
        QTest.keyClick(text_edit, Qt.Key_Tab)
        _app().processEvents()
        self.assertTrue(line.hasFocus())


class LogViewTests(QtDbTestCase):
    def test_variants_keep_terminal_scope_and_text_mode(self) -> None:
        """终端形态：纯文本 + #terminalLog（深色滚动条作用域）；纸面形态：富文本。"""
        terminal = self.track(LogView("terminal"))
        paper = self.track(LogView("paper"))
        self.assertEqual(terminal.objectName(), "terminalLog")
        self.assertFalse(terminal.acceptRichText())
        self.assertTrue(paper.acceptRichText())


if __name__ == "__main__":
    unittest.main()
