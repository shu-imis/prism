"""Prism 主窗口"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QHBoxLayout, QButtonGroup,
)
from PySide6.QtCore import Qt
from ui.styles import SIDEBAR_W, sidebar_inactive_qss, stylesheet
from ui.projects_page import ProjectsPage
from ui.process_page import ProcessPage
from ui.settings_page import SettingsPage
from ui.title_bar import TitleBar

# 关窗时仍在运行的 AI worker 挂到这里防止 GC 析构（避免 "QThread: Destroyed
# while running"），进程退出时随解释器一起回收
_orphaned_ai_workers: list = []


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 最小尺寸按内容页实测最小宽度（Step1 节点行 1017）取整上抬，横向滚动仅作兜底
        self.setMinimumSize(1040, 640)
        self.resize(1100, 700)
        self.setWindowTitle("Prism")
        self.setStyleSheet(stylesheet())
        self._setup_window()
        self._build()
        self._center()

    def changeEvent(self, event):
        if event.type() == event.Type.ActivationChange:
            active = self.isActiveWindow()
            self._title_bar.set_active(active)
            # 失焦时侧栏随标题栏一起收敛（选中态减淡、文字变灰）
            self._sidebar.setStyleSheet("" if active else sidebar_inactive_qss())
        super().changeEvent(event)

    def _setup_window(self):
        # 无边框窗口；投影由系统合成器绘制
        self.setWindowFlag(Qt.FramelessWindowHint)

    def _build(self):
        # --- 整体容器 ---
        container = QWidget()
        container.setObjectName("windowBody")
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 自定义标题栏 ---
        self._title_bar = TitleBar()
        self._title_bar.minimized.connect(self.showMinimized)
        self._title_bar.maximized.connect(self._toggle_maximize)
        self._title_bar.closed.connect(self.close)
        main_layout.addWidget(self._title_bar)

        # --- 侧边栏 + 内容区 ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_W)
        self._sidebar = sidebar
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

        for i, label in enumerate(["项目列表", "工作区", "回收站", "设置"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._go(idx))
            group.addButton(btn)
            self._btns[i] = btn
            sl.addWidget(btn)

        sl.addStretch()

        # --- 内容区 ---
        self._stack = QStackedWidget()
        self._projects = ProjectsPage()
        self._process = ProcessPage()
        self._settings = SettingsPage()
        self._stack.addWidget(self._projects)
        self._stack.addWidget(self._process)
        self._stack.addWidget(self._settings)

        self._projects.new_project.connect(lambda: (self._process.reset(), self._go(1)))
        self._projects.open_project.connect(lambda pid: (self._process.load_project(pid), self._go(1)))
        self._projects.project_deleted.connect(self._on_project_deleted)
        self._process.open_settings.connect(lambda: self._go(3))

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(sidebar)
        body.addWidget(self._stack, 1)
        main_layout.addLayout(body, 1)

        self._go(0)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # 侧栏索引 → (stack 页面索引, ProjectsPage 模式)：项目列表与回收站共用项目页
    _PAGE_MAP = [(0, "active"), (1, None), (0, "trash"), (2, None)]

    def _go(self, idx: int):
        stack_idx, page_mode = self._PAGE_MAP[idx]
        if page_mode:
            self._projects.set_mode(page_mode)
        self._stack.setCurrentIndex(stack_idx)
        for i, btn in self._btns.items():
            btn.setChecked(i == idx)

    def _on_project_deleted(self, pid: int):
        # 被删的正是工作区当前打开的项目：重置工作区，避免停留在失效项目的页面
        if self._process._pid == pid:
            self._process.reset()
            if self._stack.currentIndex() == 1:
                self._go(0)

    def closeEvent(self, event):
        """窗口关闭前安全停止工作线程，避免 PySide6 QThread 析构崩溃。"""
        self._process.stop_worker()
        # 各页面运行中的 AI worker（LLM 调用最长 180s）：断开信号并把引用挂到
        # 模块级列表，防止 GC 析构运行中的 QThread；不 wait() 阻塞关窗，
        # 进程自然退出，请求跑完即被回收
        workers = list(self._process.iter_ai_workers())
        if hasattr(self._settings, "_ai_workers"):
            workers += self._settings._ai_workers
        for worker in workers:
            try:
                worker.succeeded.disconnect()
                worker.failed.disconnect()
            except (RuntimeError, TypeError):
                pass
            _orphaned_ai_workers.append(worker)
        super().closeEvent(event)

    def _center(self):
        g = self.screen().availableGeometry()
        self.move((g.width() - self.width()) // 2, (g.height() - self.height()) // 2)
