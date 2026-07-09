"""Prism 主窗口 — Linear.app 风格全暗色

扁平最暗侧边栏 + 原生标题栏。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QSplitter,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal

from ui.styles import (
    generate_stylesheet,
    SIDEBAR_WIDTH,
)
from ui.welcome_page import WelcomePage
from ui.project_list_page import ProjectListPage
from ui.event_page import EventPage
from ui.strategy_page import StrategyPage
from ui.simulation_page import SimulationPage
from ui.result_page import ResultPage


class PageKey:
    WELCOME = "welcome"
    PROJECT_LIST = "project_list"
    EVENT = "event"
    STRATEGY = "strategy"
    SIMULATION = "simulation"
    RESULT = "result"


# ============================================================
# 侧边栏 — Linear 风格扁平深色
# ============================================================

class Sidebar(QWidget):
    """侧边栏 — 精致暗色：应用名 + 导航项（无分组标签）+ accent 圆点选中指示"""

    page_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(0)

        # ---- 应用名 ----
        app_name = QLabel("Prism")
        app_name.setObjectName("sidebarAppName")
        layout.addWidget(app_name)
        layout.addSpacing(28)

        # ---- 导航项（不分组，用间距暗示关系） ----
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}

        flat_items = [
            {"key": PageKey.WELCOME, "label": "首页"},
            {"key": PageKey.PROJECT_LIST, "label": "历史项目"},
            None,  # 分隔
            {"key": PageKey.EVENT, "label": "事件录入"},
            {"key": PageKey.STRATEGY, "label": "策略配置"},
            {"key": PageKey.SIMULATION, "label": "仿真运行"},
            {"key": PageKey.RESULT, "label": "结果分析"},
        ]

        for item in flat_items:
            if item is None:
                layout.addSpacing(20)
                continue

            btn = QPushButton(item["label"])
            btn.setProperty("class", "nav-btn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked, k=item["key"]: self._on_nav_click(k)
            )
            self._btn_group.addButton(btn)
            self._nav_buttons[item["key"]] = btn
            layout.addWidget(btn)

        layout.addStretch()

        self.set_active(PageKey.WELCOME)

    def _on_nav_click(self, key: str):
        self.set_active(key)
        self.page_changed.emit(key)

    def set_active(self, key: str):
        btn = self._nav_buttons.get(key)
        if btn:
            btn.setChecked(True)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    """Prism 主窗口 — Linear 风格全暗色"""

    MIN_WIDTH = 1024
    MIN_HEIGHT = 680

    def __init__(self):
        super().__init__()

        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1200, 800)
        self.setWindowTitle("Prism")
        self.setUnifiedTitleAndToolBarOnMac(True)

        self.setStyleSheet(generate_stylesheet())
        self._build_ui()
        self._center_on_screen()

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._navigate)

        self._stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        self._register_page(PageKey.WELCOME, WelcomePage())
        self._register_page(PageKey.PROJECT_LIST, ProjectListPage())
        self._register_page(PageKey.EVENT, EventPage())
        self._register_page(PageKey.STRATEGY, StrategyPage())
        self._register_page(PageKey.SIMULATION, SimulationPage())
        self._register_page(PageKey.RESULT, ResultPage())

        splitter.addWidget(self.sidebar)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([SIDEBAR_WIDTH, 960])
        splitter.setHandleWidth(1)

        self.setCentralWidget(splitter)

    def _register_page(self, key: str, page: QWidget):
        self._pages[key] = page
        self._stack.addWidget(page)

    def _navigate(self, key: str):
        page = self._pages.get(key)
        if page:
            self._stack.setCurrentWidget(page)

    def navigate_to(self, key: str):
        self.sidebar.set_active(key)
        self._navigate(key)

    def _center_on_screen(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
