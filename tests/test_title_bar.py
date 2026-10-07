"""标题栏行为测试：红绿灯胶囊悬停触发区与窗口按钮焦点策略。"""
from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtCore import QPoint, Qt

import ui.title_bar as title_bar
from tests.qt_helpers import QtDbTestCase, app as _app


class _FakeCursor:
    """可注入的光标位置，替代 QCursor.pos()。"""

    pt = QPoint(0, 0)

    @classmethod
    def pos(cls):
        return cls.pt


@unittest.skipUnless(title_bar.IS_MAC, "仅 macOS 标题栏存在红绿灯判定")
class MacTrafficHoverTests(QtDbTestCase):
    def test_capsule_trigger_region(self) -> None:
        """触发区为包裹三颗圆点的胶囊：灯间空隙同样唤醒，胶囊外不响应。"""
        bar = self.track(title_bar.TitleBar())
        bar.resize(1280, 36)
        bar.show()
        _app().processEvents()
        area = bar._mac_area
        self.assertEqual(area.height(), title_bar.MAC_BTN_SIZE)

        def hovered_at(x: int, y: int) -> bool:
            _FakeCursor.pt = area.mapToGlobal(QPoint(x, y))
            bar._poll_hover()
            return all(b._group_hover for b in bar._mac_buttons)

        with mock.patch.object(title_bar, "QCursor", _FakeCursor):
            self.assertTrue(hovered_at(6, 6))     # 红点圆心
            self.assertTrue(hovered_at(16, 6))    # 一、二颗之间的空隙
            self.assertTrue(hovered_at(26, 6))    # 二、三颗之间的空隙
            self.assertFalse(hovered_at(53, 6))   # 胶囊右端之外
            self.assertFalse(hovered_at(26, 14))  # 胶囊下方之外
            bar._apply_hover(None)
            self.assertFalse(any(b._group_hover for b in bar._mac_buttons))


class WindowButtonFocusTests(QtDbTestCase):
    def test_window_buttons_not_in_tab_chain(self) -> None:
        """标题栏窗口按钮不参与 Tab 序列。"""
        bar = self.track(title_bar.TitleBar())
        buttons = bar._mac_buttons or bar._win_buttons
        self.assertTrue(buttons)
        self.assertTrue(all(b.focusPolicy() == Qt.NoFocus for b in buttons))
