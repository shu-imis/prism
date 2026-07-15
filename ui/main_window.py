"""Prism 主窗口"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QSplitter, QButtonGroup,
)
from PySide6.QtCore import Qt
from ui.styles import stylesheet, SIDEBAR_W
from ui.home_page import HomePage
from ui.process_page import ProcessPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(960, 600)
        self.resize(1100, 700)
        self.setWindowTitle("Prism")
        self.setStyleSheet(stylesheet())
        self._build()
        self._center()

    def _build(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # ---- 侧边栏 ----
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_W)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        brand = QLabel("PRISM")
        brand.setObjectName("brand")
        sl.addWidget(brand)
        sl.addSpacing(16)

        self._btns: dict[int, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)

        for i, label in enumerate(["项目列表", "工作区"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._go(idx))
            group.addButton(btn)
            self._btns[i] = btn
            sl.addWidget(btn)

        sl.addStretch()
        splitter.addWidget(sidebar)

        # ---- 内容区 ----
        self._stack = QStackedWidget()
        self._home = HomePage()
        self._process = ProcessPage()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._process)

        self._home.new_project.connect(lambda: self._go(1))
        self._home.open_project.connect(lambda pid: (setattr(self._process, '_project_id', pid), self._go(1)))

        splitter.addWidget(self._stack)
        splitter.setSizes([SIDEBAR_W, 900])
        self.setCentralWidget(splitter)
        self._go(0)

    def _go(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in self._btns.items():
            btn.setChecked(i == idx)

    def _center(self):
        g = self.screen().availableGeometry()
        self.move((g.width() - self.width()) // 2, (g.height() - self.height()) // 2)
