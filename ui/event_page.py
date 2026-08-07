"""供应链搭建"""

from pathlib import Path

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
from db.models import KnowledgeRepository, ProjectRepository, invalidate_simulation_results
from llm.analysis import extract_scenario_from_docs
from llm.config import build_llm_client
from ui.ai_worker import run_ai_task
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    DangerBtn,
    DecimalInput,
    Divider,
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
            # 悬停态，与 SegmentedControl 的 QPushButton:hover 一致
            def _on_enter(l=val, s=selected_type, w=lbl):
                if s["val"] != l:
                    w.setStyleSheet(
                        f"background:{BG_HOVER};color:{TEXT_PRIMARY};"
                        "border:1px solid " + BORDER + ";padding:2px 9px;font-size:12px;"
                    )
            def _on_leave(l=val, s=selected_type, w=lbl):
                if s["val"] != l:
                    w.setStyleSheet(
                        f"background:transparent;color:{TEXT_MUTED};"
                        f"border:1px solid {BORDER};padding:2px 9px;font-size:12px;"
                    )
            lbl.enterEvent = lambda e, fn=_on_enter: fn()
            lbl.leaveEvent = lambda e, fn=_on_leave: fn()
            node_type_widgets.append((val, lbl))
            row1.addWidget(lbl)
        row1.addStretch()

        def _select_type(v, s, ws):
            s["val"] = v
            for tv, w in ws:
                if tv == v:
                    w.setStyleSheet(
                        f"background:{TEXT_PRIMARY};color:{TEXT_ON_DARK};"
                        "border:1px solid " + TEXT_PRIMARY + ";font-weight:600;"
                        "padding:2px 9px;font-size:12px;"
                    )
                else:
                    w.setStyleSheet(
                        f"background:transparent;color:{TEXT_MUTED};"
                        f"border:1px solid {BORDER};"
                        "padding:2px 9px;font-size:12px;"
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
        # 终端日志回调：默认空实现，由 ProcessPage 注入覆盖（单独实例化也能用）
        self.log = lambda *args, **kwargs: None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, PAD_XL, 0)
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
            f"可导入Markdown/TXT，最多{MAX_IMPORT_FILES}个文件，"
            f"{MAX_IMPORT_TOTAL_CHARS}字"
        ))
        btn_row = QHBoxLayout()
        self._import_btn = SecondaryBtn("导入背景文档")
        self._import_btn.clicked.connect(self._import_docs)
        btn_row.addWidget(self._import_btn)
        self._ai_btn = GhostBtn("AI 分析并自动填写")
        self._ai_btn.clicked.connect(self._ai_fill)
        btn_row.addWidget(self._ai_btn)
        btn_row.addStretch()
        card.add_layout(btn_row)

        # 已导入文档清单（导入前为空，不占视觉空间）
        self._docs_layout = QVBoxLayout()
        self._docs_layout.setSpacing(PAD_XS)
        card.add_layout(self._docs_layout)

        # 已入库的知识库分块（保存文档时写入，供仿真 RAG 检索）
        self._kb_layout = QVBoxLayout()
        self._kb_layout.setSpacing(PAD_XS)
        card.add_layout(self._kb_layout)

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
        # 清空上个项目残留的导入文档，避免误存进当前项目
        self._imported = []
        self._render_imported_docs()
        self._render_knowledge_base()
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
        self._render_imported_docs()
        self._render_knowledge_base()
        self._title.clear()
        self._bg.clear()
        self._node_editor.set_nodes(DEFAULT_NODES)
        self._inv.setValue(75)
        self._cost.setValue(50)
        self._svc.setValue(0.85)

    def _import_docs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "导入文档", "", "文档(*.md *.txt)"
        )
        if not files:
            return
        # 大文件读取耗时，放 worker 线程执行避免冻结界面
        self._import_btn.setEnabled(False)
        self._import_btn.setText("导入中…")
        run_ai_task(
            self,
            lambda: import_documents(files),
            self._on_docs_imported,
            self._on_docs_import_error,
        )

    def _reset_import_btn(self):
        self._import_btn.setEnabled(True)
        self._import_btn.setText("导入背景文档")

    def _on_docs_imported(self, imported):
        self._reset_import_btn()
        self._imported = imported
        self._render_imported_docs()
        self.log(f"已导入 {len(self._imported)} 个文档")

    def _on_docs_import_error(self, err):
        self._reset_import_btn()
        self.log(f"导入失败：{err}", is_error=True)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                EventPage._clear_layout(item.layout())

    def _render_imported_docs(self):
        """把已导入文档渲染成可见清单（文件名 + 字数 + 清除入口）。"""
        self._clear_layout(self._docs_layout)

        if not self._imported:
            return

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(Caption(f"已导入 {len(self._imported)} 个文档："))
        clear_btn = GhostBtn("清除")
        clear_btn.clicked.connect(self._clear_imported_docs)
        header.addWidget(clear_btn)
        header.addStretch()
        self._docs_layout.addLayout(header)

        for doc in self._imported:
            name = Path(doc.path).name
            self._docs_layout.addWidget(Caption(f"{name}（{len(doc.text)} 字）"))

    def _clear_imported_docs(self):
        self._imported = []
        self._render_imported_docs()
        self.log("已清除导入的文档")

    # --- 知识库（已入库分块） ---

    def _render_knowledge_base(self):
        """展示当前项目已入库的知识分块（按来源文档聚合），支持清空。"""
        self._clear_layout(self._kb_layout)
        if not self._pid:
            return
        chunks = KnowledgeRepository().list_by_project(self._pid)
        if not chunks:
            return

        by_source: dict[str, list] = {}
        for chunk in chunks:
            by_source.setdefault(chunk.source, []).append(chunk)

        self._kb_layout.addWidget(Divider())
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        # 不用 Caption（自动换行会折成多行）：标题保持单行
        title = QLabel(
            f"知识库（供仿真检索）：{len(by_source)} 个文档 · {len(chunks)} 个分块"
        )
        title.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        header.addWidget(title)
        clear_btn = GhostBtn("清空知识库")
        clear_btn.clicked.connect(self._clear_knowledge_base)
        header.addWidget(clear_btn)
        header.addStretch()
        self._kb_layout.addLayout(header)

        for source, items in by_source.items():
            total_chars = sum(len(item.content) for item in items)
            self._kb_layout.addWidget(Caption(f"{Path(source).name}（{len(items)} 块 · {total_chars} 字）"))

    def _clear_knowledge_base(self):
        if not self._pid:
            return
        KnowledgeRepository().replace_for_project(self._pid, [])
        self._render_knowledge_base()
        self.log("已清空项目知识库")

    # --- AI 分析文档并自动填写 ---

    def _ai_fill(self):
        docs_text = "\n\n".join(d.text for d in self._imported).strip()
        if not docs_text:
            docs_text = self._bg.toPlainText().strip()
        if not docs_text:
            self.log("请先导入文档或填写供应链背景", is_error=True)
            return
        client = build_llm_client()
        if client is None:
            self.log("未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key", is_error=True)
            return
        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("AI 分析中…")
        pid = self._pid
        run_ai_task(
            self,
            lambda: extract_scenario_from_docs(client, docs_text),
            lambda sc: self._on_ai_scenario(sc, pid),
            self._on_ai_error,
        )

    def _reset_ai_btn(self):
        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI 分析并自动填写")

    def _on_ai_scenario(self, sc, pid):
        self._reset_ai_btn()
        # 等待期间用户可能已切换项目：pid 不匹配则忽略结果，避免旧数据填进新页面
        if pid != self._pid:
            return
        if sc.get("title"):
            self._title.setText(sc["title"])
        if sc.get("industry"):
            self._industry.setText(sc["industry"])
        if sc.get("background"):
            self._bg.setPlainText(sc["background"])
        self._inv.setValue(sc.get("initial_inventory", 75))
        self._cost.setValue(sc.get("baseline_cost", 50))
        self._svc.setValue(sc.get("baseline_service_level", 0.85))
        if sc.get("nodes"):
            self._node_editor.set_nodes(sc["nodes"])
        self.log("AI 已完成文档分析并自动填写，请核对后保存")

    def _on_ai_error(self, err):
        self._reset_ai_btn()
        self.log(f"AI 分析失败：{err}", is_error=True)

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
            # update_scenario 为全量替换：先读旧 scenario 再仅覆盖本步字段，
            # 保留 Step2 写入的 agents_config / seed_events
            project = repo.get_by_id(self._pid)
            if project is None:
                # 项目已在首页被删除：不保存、不崩，提示用户重新创建
                self.log("项目已被删除，请回到首页重新创建或打开其他项目", is_error=True)
                return
            merged = dict(project.scenario)
            merged.update(sc)
            sc = merged
            # 场景变更使旧仿真结果失效：清轮次/检查点/报告并回到草稿
            if project.status in ("completed", "interrupted"):
                invalidate_simulation_results(self._pid)
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
        self._render_knowledge_base()

        self.project_saved.emit(pid)
