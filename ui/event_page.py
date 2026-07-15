"""供应链搭建"""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.document_importer import (
    MAX_IMPORT_FILES,
    MAX_IMPORT_TOTAL_CHARS,
    chunk_text,
    import_documents,
)
from db.models import KnowledgeRepository, ProjectRepository
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    Input,
    PrimaryBtn,
    SecondaryBtn,
    Title,
)


class EventPage(QWidget):
    project_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._imported = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;padding:0;margin:0;}"
        )

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, PAD_XL, 0)
        inner_layout.setSpacing(PAD_SM)

        card = Card()
        card.add(Title("供应链搭建", 14))

        card.add(QLabel("供应链名称"))
        self._title = Input("例：电子产品供应链推演")
        card.add(self._title)

        card.add(QLabel("行业"))
        self._industry = QComboBox()
        self._industry.setEditable(True)
        self._industry.addItems([
            "电子制造", "汽车", "快消/零售", "医药", "农产品", "其他",
        ])
        card.add(self._industry)

        card.add(QLabel("供应链背景"))
        self._bg = QTextEdit()
        self._bg.setPlaceholderText("描述供应链背景、结构和当前运行状况...")
        self._bg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.add(self._bg)

        card.add(Caption(
            f"可导入PDF/Word/Markdown/TXT，最多{MAX_IMPORT_FILES}个文件，"
            f"{MAX_IMPORT_TOTAL_CHARS}字"
        ))
        import_btn = SecondaryBtn("导入背景文档")
        import_btn.clicked.connect(self._import_docs)
        card.add(import_btn)

        card.add(QLabel("供应链节点（JSON格式）"))
        self._nodes = QTextEdit()
        self._nodes.setPlaceholderText(
            '[{"name":"供应商A","type":"supplier","inventory":80,'
            '"lead_time":2,"capacity":100},...]'
        )
        card.add(self._nodes)

        hr = QHBoxLayout()
        hr.addWidget(QLabel("初始库存水平"))
        self._inv = QSpinBox()
        self._inv.setRange(0, 100)
        self._inv.setValue(75)
        hr.addWidget(self._inv)

        hr.addWidget(QLabel("基线成本指数"))
        self._cost = QSpinBox()
        self._cost.setRange(0, 100)
        self._cost.setValue(50)
        hr.addWidget(self._cost)

        hr.addWidget(QLabel("基线服务水平"))
        self._svc = QDoubleSpinBox()
        self._svc.setRange(0, 1)
        self._svc.setSingleStep(0.05)
        self._svc.setDecimals(2)
        self._svc.setValue(0.85)
        hr.addWidget(self._svc)
        hr.addStretch()
        card.add_layout(hr)

        inner_layout.addWidget(card)
        inner_layout.addStretch()

        self._err = QLabel("")
        self._err.setStyleSheet(f"color:{COLOR_RED};font-size:12px;")
        self._err.setVisible(False)
        inner_layout.addWidget(self._err)

        self._save_btn = PrimaryBtn("保存并配置决策方案 →")
        self._save_btn.clicked.connect(self._save)
        inner_layout.addWidget(self._save_btn)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def load_project(self, pid):
        p = ProjectRepository().get_by_id(pid)
        if not p:
            return
        self._pid = p.id
        s = p.scenario
        self._title.setText(s.get("title", ""))
        self._bg.setPlainText(s.get("background", ""))
        self._inv.setValue(s.get("initial_inventory", 75))
        self._cost.setValue(s.get("baseline_cost", 50))
        self._svc.setValue(s.get("baseline_service_level", 0.85))
        self._nodes.setPlainText(
            json.dumps(s.get("nodes", []), ensure_ascii=False, indent=2)
        )

    def reset_for_new_project(self):
        self._pid = None
        self._imported = []
        self._title.clear()
        self._bg.clear()
        self._nodes.clear()
        self._inv.setValue(75)
        self._cost.setValue(50)
        self._svc.setValue(0.85)

    def _import_docs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "导入文档", "", "文档(*.pdf *.docx *.md *.txt)"
        )
        if files:
            try:
                self._imported = import_documents(files)
                self._save_btn.setText(
                    f"已导入{len(self._imported)}个文档 — 保存并继续 →"
                )
            except Exception as e:
                self._err.setText(f"导入失败：{e}")
                self._err.setVisible(True)

    def _save(self):
        t = self._title.text().strip()
        if len(t) > 80:
            self._err.setText("名称不能超过80字")
            self._err.setVisible(True)
            return

        bg = self._bg.toPlainText().strip()
        if not bg:
            self._err.setText("请填写供应链背景")
            self._err.setVisible(True)
            return

        nodes_text = self._nodes.toPlainText().strip()
        try:
            nodes = json.loads(nodes_text) if nodes_text else []
        except json.JSONDecodeError:
            self._err.setText("节点JSON格式错误")
            self._err.setVisible(True)
            return

        sc = {
            "title": t,
            "industry": self._industry.currentText(),
            "background": bg,
            "nodes": nodes,
            "initial_inventory": self._inv.value(),
            "baseline_cost": self._cost.value(),
            "baseline_service_level": self._svc.value(),
        }

        repo = ProjectRepository()
        if self._pid:
            p = repo.update_scenario(self._pid, sc)
            pid = p.id
        else:
            p = repo.create(t, sc)
            pid = p.id
            self._pid = pid

        if self._imported:
            KnowledgeRepository().replace_for_project(
                pid,
                [
                    {"source": d.path, "chunk_index": i, "content": c}
                    for d in self._imported
                    for i, c in enumerate(chunk_text(d.text))
                ],
            )

        self.project_saved.emit(pid)
