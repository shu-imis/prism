"""供应链搭建"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
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
    DangerBtn,
    DecimalInput,
    GhostBtn,
    Input,
    NumberInput,
    PrimaryBtn,
    SecondaryBtn,
    Title,
)

NODE_TYPES = [
    ("supplier", "原材料供应商"),
    ("manufacturer", "制造商"),
    ("distributor", "分销商"),
    ("retailer", "零售商"),
    ("logistics", "物流服务商"),
    ("consumer", "消费者"),
    ("regulator", "监管机构"),
]

DEFAULT_NODES = [
    {"name": "节点 1", "type": "supplier", "inventory": 80, "lead_time": 2, "capacity": 100, "cost_index": 52, "downstream": ["节点 2"]},
    {"name": "节点 2", "type": "manufacturer", "inventory": 60, "lead_time": 3, "capacity": 150, "cost_index": 58, "upstream": ["节点 1"], "downstream": ["节点 3"]},
    {"name": "节点 3", "type": "distributor", "inventory": 50, "lead_time": 1, "capacity": 200, "cost_index": 54, "upstream": ["节点 2"], "downstream": ["节点 4"]},
    {"name": "节点 4", "type": "retailer", "inventory": 40, "lead_time": 1, "capacity": 80, "cost_index": 49, "upstream": ["节点 3"]},
]


def _format_refs(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item).strip() for item in value if str(item).strip())


def _parse_refs(text):
    return [part.strip() for part in str(text).split(",") if part.strip()]


class NodeEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = []
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(PAD_SM)

    def add_node(self, data=None):
        d = data or {
            "name": "", "type": "supplier",
            "inventory": 50, "cost_index": 50,
            "lead_time": 2, "capacity": 100,
            "upstream": [], "downstream": [],
        }
        card = Card(padding=PAD_MD)

        hdr = QHBoxLayout()
        hdr.addWidget(Title(f"节点 {len(self._nodes) + 1}", 12))
        hdr.addStretch()
        if len(self._nodes) >= 1:
            rm = DangerBtn("删除")
            rm.clicked.connect(lambda: self._remove(card))
            hdr.addWidget(rm)
        card.add_layout(hdr)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("名称"))
        name = Input("如：华东仓")
        name.setText(str(d.get("name", "")))
        row1.addWidget(name)

        row1.addWidget(QLabel("类型"))
        type_val = d.get("type", "supplier")
        selected_type = {"val": type_val}
        node_type_widgets = []
        for val, label in NODE_TYPES:
            lbl = QLabel(label)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.setFixedHeight(BTN_H)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.mousePressEvent = (
                lambda e, v=val, s=selected_type, ws=node_type_widgets:
                _select_type(v, s, ws)
            )
            node_type_widgets.append((val, lbl))
            row1.addWidget(lbl)
        row1.addStretch()

        def _select_type(v, s, ws):
            s["val"] = v
            for tv, w in ws:
                if tv == v:
                    w.setStyleSheet(
                        f"background:{TEXT_PRIMARY};color:{TEXT_ON_DARK};"
                        "padding:2px 10px;font-size:12px;"
                    )
                else:
                    w.setStyleSheet(
                        f"background:transparent;color:{TEXT_MUTED};"
                        "padding:2px 10px;font-size:12px;"
                    )
        _select_type(type_val, selected_type, node_type_widgets)

        card.add_layout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("库存"))
        inv = NumberInput(value=d.get("inventory", 50), min_val=0, max_val=100)
        row2.addWidget(inv)

        row2.addWidget(QLabel("交货周期"))
        lead = NumberInput(value=d.get("lead_time", 2), min_val=0, max_val=10)
        row2.addWidget(lead)

        row2.addWidget(QLabel("产能上限"))
        cap = NumberInput(value=d.get("capacity", 100), min_val=0, max_val=200)
        row2.addWidget(cap)

        row2.addWidget(QLabel("成本指数"))
        cost_idx = NumberInput(value=d.get("cost_index", d.get("cost", 50)), min_val=0, max_val=100)
        row2.addWidget(cost_idx)
        row2.addStretch()
        card.add_layout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("上游节点"))
        up = QLineEdit(_format_refs(d.get("upstream", [])))
        up.setPlaceholderText("名称，逗号分隔")
        row3.addWidget(up)

        row3.addWidget(QLabel("下游节点"))
        down = QLineEdit(_format_refs(d.get("downstream", [])))
        down.setPlaceholderText("名称，逗号分隔")
        row3.addWidget(down)
        row3.addStretch()
        card.add_layout(row3)

        self._nodes.append({
            "card": card,
            "name": name,
            "type": selected_type,
            "inventory": inv,
            "lead_time": lead,
            "capacity": cap,
            "cost": cost_idx,
            "upstream": up,
            "downstream": down,
        })
        self._layout.insertWidget(self._layout.count(), card)
        self._update_nums()

    def _remove(self, card):
        for i, nd in enumerate(self._nodes):
            if nd["card"] is card:
                self._layout.removeWidget(card)
                card.deleteLater()
                del self._nodes[i]
                break
        self._update_nums()

    def _update_nums(self):
        for i, nd in enumerate(self._nodes):
            nd["card"].findChild(QLabel).setText(f"节点 {i + 1}")

    def get_nodes(self):
        result = []
        for nd in self._nodes:
            result.append({
                "name": nd["name"].text().strip(),
                "type": nd["type"]["val"],
                "inventory": nd["inventory"].value(),
                "lead_time": nd["lead_time"].value(),
                "capacity": nd["capacity"].value(),
                "cost_index": nd["cost"].value(),
                "upstream": _parse_refs(nd["upstream"].text()),
                "downstream": _parse_refs(nd["downstream"].text()),
            })
        return result

    def set_nodes(self, nodes):
        while self._nodes:
            nd = self._nodes.pop()
            self._layout.removeWidget(nd["card"])
            nd["card"].deleteLater()
        for n in nodes:
            self.add_node(n)

    def clear(self):
        self.set_nodes([])


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
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(PAD_SM)

        card = Card()
        card.add(Title("供应链搭建", 14))

        card.add(QLabel("供应链名称"))
        self._title = Input("如：电子产品供应链推演")
        card.add(self._title)

        card.add(QLabel("行业"))
        self._industry = Input("如：电子制造")
        card.add(self._industry)

        card.add(QLabel("供应链背景"))
        self._bg = QTextEdit()
        self._bg.setPlaceholderText("描述供应链背景、结构和当前运行状况……")
        self._bg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.add(self._bg)

        card.add(Caption(
            f"可导入PDF/Word/Markdown/TXT，最多{MAX_IMPORT_FILES}个文件，"
            f"{MAX_IMPORT_TOTAL_CHARS}字"
        ))
        import_btn = SecondaryBtn("导入背景文档")
        import_btn.clicked.connect(self._import_docs)
        card.add(import_btn)

        inner_layout.addWidget(card)

        node_card = Card()
        node_card.add(Title("供应链节点", 14))

        self._node_editor = NodeEditor()
        for n in DEFAULT_NODES:
            self._node_editor.add_node(n)
        node_card.add(self._node_editor)

        add_node_btn = GhostBtn("＋ 添加节点")
        add_node_btn.clicked.connect(lambda: self._node_editor.add_node())
        node_card.add(add_node_btn)

        inner_layout.addWidget(node_card)

        param_card = Card()
        hr = QHBoxLayout()
        hr.addWidget(QLabel("初始库存水平"))
        self._inv = NumberInput(value=75, min_val=0, max_val=100)
        hr.addWidget(self._inv)

        hr.addWidget(QLabel("基线成本指数"))
        self._cost = NumberInput(value=50, min_val=0, max_val=100)
        hr.addWidget(self._cost)

        hr.addWidget(QLabel("基线服务水平"))
        self._svc = DecimalInput(value=0.85, min_val=0, max_val=1, step=0.05, decimals=2)
        hr.addWidget(self._svc)
        hr.addStretch()
        param_card.add_layout(hr)

        inner_layout.addWidget(param_card)
        inner_layout.addStretch()

        self._save_btn = PrimaryBtn("保存并配置行为体性格 →")
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
        self._industry.setText(s.get("industry", ""))
        self._bg.setPlainText(s.get("background", ""))
        self._inv.setValue(s.get("initial_inventory", 75))
        self._cost.setValue(s.get("baseline_cost", 50))
        self._svc.setValue(s.get("baseline_service_level", 0.85))
        self._node_editor.set_nodes(s.get("nodes", DEFAULT_NODES))

    def reset_for_new_project(self):
        self._pid = None
        self._imported = []
        self._title.clear()
        self._bg.clear()
        self._node_editor.set_nodes(DEFAULT_NODES)
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
                    f"已导入 {len(self._imported)} 个文档，保存并继续 →"
                )
            except Exception as e:
                self.log(f"导入失败：{e}", is_error=True)
                return

    def _save(self):
        t = self._title.text().strip()
        if len(t) > 80:
            self.log("名称请勿超过 80 字", is_error=True)
            return

        bg = self._bg.toPlainText().strip()
        if not bg:
            self.log("请填写供应链背景", is_error=True)
            return

        nodes = self._node_editor.get_nodes()
        for n in nodes:
            if not n["name"]:
                self.log("请填写所有节点名称", is_error=True)
                return

        sc = {
            "title": t,
            "industry": self._industry.text(),
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
