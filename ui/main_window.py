"""Prism 主窗口"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QHBoxLayout, QButtonGroup, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ui.styles import stylesheet, SIDEBAR_W
from ui.home_page import HomePage
from ui.process_page import ProcessPage
from ui.settings_page import SettingsPage
from ui.title_bar import TitleBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(960, 600)
        self.resize(1100, 700)
        self.setWindowTitle("Prism")
        self.setStyleSheet(stylesheet())
        self._setup_window()
        self._build()
        self._center()

    def changeEvent(self, event):
        if event.type() == event.Type.ActivationChange:
            self._title_bar.set_active(self.isActiveWindow())
        super().changeEvent(event)

    def _setup_window(self):
        # 无边框窗口 + 透明背景，投影由容器自身绘制
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _build(self):
        # ---- 投影包裹层：10px 透明边距供阴影伸展 ----
        shadow = QWidget(self)
        self.setCentralWidget(shadow)
        shadow_layout = QVBoxLayout(shadow)
        shadow_layout.setContentsMargins(10, 10, 10, 10)
        shadow_layout.setSpacing(0)

        # ---- 整体容器 ----
        container = QWidget()
        container.setObjectName("windowBody")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 自定义标题栏 ----
        self._title_bar = TitleBar()
        self._title_bar.minimized.connect(self.showMinimized)
        self._title_bar.maximized.connect(self._toggle_maximize)
        self._title_bar.closed.connect(self.close)
        main_layout.addWidget(self._title_bar)

        # ---- 侧边栏 + 内容区 ----
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

        for i, label in enumerate(["项目列表", "工作区", "设置"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._go(idx))
            group.addButton(btn)
            self._btns[i] = btn
            sl.addWidget(btn)

        sl.addStretch()

        # ---- 内容区 ----
        self._stack = QStackedWidget()
        self._home = HomePage()
        self._process = ProcessPage()
        self._settings = SettingsPage()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._process)
        self._stack.addWidget(self._settings)

        self._home.new_project.connect(lambda: (self._process.reset(), self._go(1)))
        self._home.open_project.connect(lambda pid: (self._process.load_project(pid), self._go(1)))
        self._process.open_settings.connect(lambda: self._go(2))

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(sidebar)
        body.addWidget(self._stack, 1)
        main_layout.addLayout(body, 1)
        shadow_layout.addWidget(container)

        # ---- 投影效果（弥散投影，与 QMenu 原生阴影同层次） ----
        drop_shadow = QGraphicsDropShadowEffect(container)
        drop_shadow.setBlurRadius(24)
        drop_shadow.setOffset(0, 4)
        drop_shadow.setColor(QColor(0, 0, 0, 60))
        container.setGraphicsEffect(drop_shadow)

        self._go(0)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _go(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in self._btns.items():
            btn.setChecked(i == idx)

    def closeEvent(self, event):
        """窗口关闭前安全停止工作线程，避免 PySide6 QThread 析构崩溃。"""
        self._process.stop_worker()
        super().closeEvent(event)

    def _center(self):
        g = self.screen().availableGeometry()
        self.move((g.width() - self.width()) // 2, (g.height() - self.height()) // 2)
