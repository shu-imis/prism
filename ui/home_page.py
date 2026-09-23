"""首页 — 项目列表"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QGridLayout, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QTimer
from ui.styles import *
from ui.widgets import Title, Caption, ConfirmDialog, PrimaryBtn, PopupMenu, StatusDot
from db.models import ProjectRepository, is_valid_json


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

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setContentsMargins(PAD_XL, 0, PAD_XL, 0)
        self._grid.setSpacing(PAD_MD)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll, 1)
        self._current_cols = 1
        self._last_cols = 0

        # 拖拽改变尺寸时防抖：尺寸稳定后才重建网格，避免拖动过程中反复全量重建
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._on_resize_settled)

        self.refresh()

    def _columns(self) -> int:
        """根据滚动区宽度动态计算列数（每列至少 240px + 间距）。"""
        vw = self._scroll.viewport().width() - 2 * PAD_XL
        return max(1, vw // (240 + PAD_MD))

    def refresh(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        projects = self._repo.list_all()
        cols = self._columns()

        # 先清除所有历史列的拉伸因子，避免列数减少时残留的 stretch 把内容挤偏
        for col in range(max(cols, self._last_cols)):
            self._grid.setColumnStretch(col, 0)
        self._last_cols = cols

        if not projects:
            empty = QLabel("暂无项目\n点击「＋ 新建项目」创建")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; padding: 40px;")
            for col in range(cols):
                self._grid.setColumnStretch(col, 1)
            self._grid.setRowStretch(0, 1)
            self._grid.addWidget(empty, 0, 0, 1, cols, Qt.AlignCenter)
            return

        self._grid.setRowStretch(0, 0)
        for i, proj in enumerate(projects):
            btn = QPushButton()
            btn.setStyleSheet(
                f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
                f"QPushButton:hover {{ border-color: {TEXT_PRIMARY}; }}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(240, 140)
            btn.clicked.connect(lambda checked, pid=proj.id: self.open_project.emit(pid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, b=btn, pid=proj.id, name=proj.name: self._on_context_menu(b, pos, pid, name))

            card_layout = QVBoxLayout(btn)
            card_layout.setContentsMargins(PAD_MD, PAD_MD, PAD_MD, PAD_MD)
            card_layout.setSpacing(PAD_XS)

            sr = QHBoxLayout()
            sr.addWidget(StatusDot(STATUS_COLORS.get(proj.status, TEXT_MUTED)))
            sl = QLabel(STATUS_LABELS.get(proj.status, proj.status))
            sl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {STATUS_COLORS.get(proj.status, TEXT_MUTED)};")
            sr.addWidget(sl)
            sr.addStretch()
            card_layout.addLayout(sr)

            name = QLabel(proj.name)
            name.setWordWrap(True)
            name.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
            card_layout.addWidget(name)

            industry = proj.scenario.get("industry", "")
            if industry:
                card_layout.addWidget(Caption(industry))

            if not is_valid_json(proj.scenario_json):
                warn = Caption("数据异常：场景信息已损坏")
                warn.setStyleSheet(f"color: {COLOR_RED};")
                card_layout.addWidget(warn)

            card_layout.addStretch()

            date_str = (proj.created_at or "")[:10]
            card_layout.addWidget(Caption(date_str))

            self._grid.addWidget(btn, i // cols, i % cols)

    def resizeEvent(self, event):
        """宽度变化时重启防抖定时器，列数稳定后由 _on_resize_settled 决定是否重建。"""
        super().resizeEvent(event)
        if hasattr(self, '_resize_timer'):
            self._resize_timer.start()

    def _on_resize_settled(self):
        new_cols = self._columns()
        # 只有列数真正变化时才刷新，避免每次 resize 都重建
        if new_cols != self._current_cols:
            self._current_cols = new_cols
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._current_cols = self._columns()
        self.refresh()

    def _on_context_menu(self, btn, pos, pid, name):
        menu = PopupMenu(self)
        menu.add_action("删除", lambda: self._confirm_delete(pid, name))
        menu.popup(btn.mapToGlobal(pos))

    def _confirm_delete(self, pid, name):
        # 软删除仅标记 deleted_at，应用内无恢复入口，需二次确认
        if ConfirmDialog.confirm(
            self,
            "删除项目",
            f"确定删除项目「{name}」吗？\n项目将从列表移除，且无法在应用内恢复。",
            ok_text="删除",
            danger=True,
        ):
            self._repo.soft_delete(pid)
            self.refresh()
