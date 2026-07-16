"""首页 — 项目列表"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QGridLayout, QPushButton, QMenu,
)
from PySide6.QtCore import Qt, Signal
from ui.styles import *
from ui.widgets import Title, Caption, PrimaryBtn, StatusDot
from db.models import ProjectRepository

_STATUS_COLORS = {"draft": COLOR_ORANGE, "running": COLOR_BLUE, "completed": COLOR_GREEN}
_STATUS_LABELS = {"draft": "草稿", "running": "运行中", "completed": "已完成"}


class HomePage(QWidget):
    new_project = Signal()
    open_project = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repo = ProjectRepository()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, PAD_XL, 0, PAD_XL)
        layout.setSpacing(PAD_LG)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(PAD_XL, 0, PAD_XL, 0)
        hdr.addWidget(Title("项目列表", 18))
        hdr.addStretch()
        new_btn = PrimaryBtn("＋ 新建项目")
        new_btn.clicked.connect(lambda: self.new_project.emit())
        hdr.addWidget(new_btn)
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._inner)
        self._grid.setContentsMargins(PAD_XL, 0, PAD_XL, 0)
        self._grid.setSpacing(PAD_MD)
        scroll.setWidget(self._inner)
        layout.addWidget(scroll, 1)
        self.refresh()

    def refresh(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        projects = self._repo.list_all()
        if not projects:
            empty = QLabel("暂无项目\n点击「＋ 新建项目」创建")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; padding: 40px;")
            self._grid.addWidget(empty, 0, 0)
            return

        for i, proj in enumerate(projects):
            btn = QPushButton()
            btn.setObjectName("")
            btn.setStyleSheet(
                f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
                f"QPushButton:hover {{ border-color: {TEXT_PRIMARY}; }}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(240, 140)
            btn.clicked.connect(lambda checked, pid=proj.id: self.open_project.emit(pid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, b=btn, pid=proj.id: self._on_context_menu(b, pos, pid))

            card_layout = QVBoxLayout(btn)
            card_layout.setContentsMargins(PAD_MD, PAD_MD, PAD_MD, PAD_MD)
            card_layout.setSpacing(PAD_XS)

            sr = QHBoxLayout()
            sr.addWidget(StatusDot(_STATUS_COLORS.get(proj.status, TEXT_MUTED)))
            sl = QLabel(_STATUS_LABELS.get(proj.status, proj.status))
            sl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {_STATUS_COLORS.get(proj.status, TEXT_MUTED)};")
            sr.addWidget(sl)
            sr.addStretch()
            card_layout.addLayout(sr)

            name = QLabel(proj.name)
            name.setWordWrap(True)
            name.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
            card_layout.addWidget(name)

            card_layout.addStretch()

            date_str = (proj.created_at or "")[:10]
            card_layout.addWidget(Caption(date_str))

            self._grid.addWidget(btn, i // 3, i % 3)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _on_context_menu(self, btn, pos, pid):
        menu = QMenu()
        menu.setStyleSheet(f"QMenu{{background:{BG_SURFACE};border:1px solid {BORDER};padding:4px;}} QMenu::item{{padding:6px 12px;color:{TEXT_PRIMARY};}} QMenu::item:selected{{background:{TEXT_PRIMARY};color:{TEXT_ON_DARK};}}")
        delete_action = menu.addAction("删除")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == delete_action:
            self._repo.soft_delete(pid)
            self.refresh()
