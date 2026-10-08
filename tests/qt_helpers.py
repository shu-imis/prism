"""Qt 离屏测试共享基建。

QT_QPA_PLATFORM=offscreen 须在首个 QApplication 创建前设置；QtDbTestCase
为每个用例提供独立临时数据库（顶替默认单例）并负责销毁窗口件。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from db.database import Database


def app() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


class QtDbTestCase(unittest.TestCase):
    """每个用例独立临时数据库顶替默认单例，用例结束销毁窗口件。"""

    def setUp(self) -> None:
        app()
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Database(Path(self._tmp.name) / "test.db")
        Database._default_instance = self._db
        self._db.migrate()
        self._widgets: list = []

    def tearDown(self) -> None:
        for w in self._widgets:
            w.deleteLater()
        app().sendPostedEvents(None, QEvent.DeferredDelete)
        app().processEvents()
        self._db.close()
        Database._default_instance = None
        self._tmp.cleanup()

    def track(self, widget):
        self._widgets.append(widget)
        return widget
