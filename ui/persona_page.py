"""行为体性格配置"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_config
from core.agent import AGENT_TEMPLATES
from core.agent_factory import AgentFactory
from db.models import ProjectRepository
from llm.analysis import generate_agent_config
from llm.config import build_llm_client
from ui.ai_worker import run_ai_task
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
    SegmentedControl,
    Title,
)

STANCES = [
    ("aggressive", "激进"),
    ("cautious", "保守"),
    ("cooperative", "协作"),
    ("defensive", "防御"),
]

MAX_SEED_EVENTS = 3


class PersonaPage(QWidget):
    agents_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._agent_cards = []
        self._seed_rows = []
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
        self._il = QVBoxLayout(inner)
        self._il.setContentsMargins(0, 0, 0, 0)
        self._il.setSpacing(PAD_SM)

        card = Card()
        header = QHBoxLayout()
        header.addWidget(Title("行为体性格配置", 14))
        header.addStretch()
        self._ai_btn = GhostBtn("AI 生成行为体配置")
        self._ai_btn.clicked.connect(self._ai_generate)
        header.addWidget(self._ai_btn)
        card.add_layout(header)
        card.add(Caption("调整 7 个行为体的决策倾向、活跃度、影响力与角色画像，观察单条供应链的演化"))
        self._il.addWidget(card)

        for tmpl in AGENT_TEMPLATES:
            self._il.addWidget(self._build_agent_card(tmpl))

        # --- 种子事件 ---
        self._seed_card = Card()
        self._seed_card.add(Title("种子事件", 14))
        self._seed_card.add(Caption("在指定周期向供应链注入外部干预（最多 3 条）"))
        self._seed_layout = QVBoxLayout()
        self._seed_layout.setSpacing(PAD_SM)
        self._seed_card.add_layout(self._seed_layout)
        self._seed_add_btn = GhostBtn("＋ 添加种子事件")
        self._seed_add_btn.clicked.connect(lambda: self._add_seed_row())
        self._seed_card.add(self._seed_add_btn)
        self._il.addWidget(self._seed_card)

        self._il.addStretch()

        br = QHBoxLayout()
        br.addStretch()
        self._save_btn = PrimaryBtn("保存并开始仿真 →")
        self._save_btn.clicked.connect(self._save)
        br.addWidget(self._save_btn)
        self._il.addLayout(br)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _build_agent_card(self, tmpl):
        card = Card(padding=PAD_MD)

        hdr = QHBoxLayout()
        hdr.addWidget(Title(tmpl["name"], 13))
        role = Caption(tmpl["role"])
        role.setStyleSheet(
            f"font-size:11px;color:{TEXT_MUTED};border:1px solid {BORDER};padding:1px 8px;"
        )
        hdr.addWidget(role)
        hdr.addStretch()
        card.add_layout(hdr)

        row = QHBoxLayout()
        row.addWidget(QLabel("决策倾向"))
        stance = SegmentedControl(STANCES)
        stance.set_value(tmpl["decision_stance"])
        row.addWidget(stance)

        row.addWidget(QLabel("活跃度"))
        activity = QSlider(Qt.Horizontal)
        activity.setRange(0, 100)
        activity.setValue(int(tmpl["activity"] * 100))
        activity.setFixedWidth(140)
        activity_value = QLabel(f"{activity.value()}%")
        activity_value.setFixedWidth(40)
        activity_value.setStyleSheet(
            f"font-family:'JetBrains Mono';font-size:12px;color:{TEXT_PRIMARY};"
        )
        activity.valueChanged.connect(lambda v, lbl=activity_value: lbl.setText(f"{v}%"))
        row.addWidget(activity)
        row.addWidget(activity_value)

        row.addWidget(QLabel("影响力"))
        influence = DecimalInput(
            value=tmpl["influence"], min_val=0.5, max_val=3.0, step=0.1, decimals=1
        )
        row.addWidget(influence)
        row.addStretch()
        card.add_layout(row)

        card.add(QLabel("角色画像"))
        profile = QTextEdit()
        profile.setPlainText(tmpl["profile"])
        profile.setMaximumHeight(90)
        card.add(profile)

        self._agent_cards.append({
            "id": tmpl["id"],
            "stance": stance,
            "activity": activity,
            "influence": influence,
            "profile": profile,
        })
        return card

    def _add_seed_row(self, data=None):
        if len(self._seed_rows) >= MAX_SEED_EVENTS:
            return
        d = data or {}

        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(PAD_SM)

        content = Input("事件内容，如：港口罢工导致物流中断")
        content.setText(str(d.get("content", "")))
        row.addWidget(content, 1)

        row.addWidget(QLabel("注入周期"))
        cycle = NumberInput(value=int(d.get("cycle", 1)), min_val=1, max_val=app_config.sim.max_rounds)
        row.addWidget(cycle)

        rm = DangerBtn("删除")
        rm.clicked.connect(lambda: self._remove_seed_row(row_widget))
        row.addWidget(rm)

        self._seed_rows.append({"widget": row_widget, "content": content, "cycle": cycle})
        self._seed_layout.addWidget(row_widget)
        self._update_seed_btn()

    def _remove_seed_row(self, row_widget):
        for i, sr in enumerate(self._seed_rows):
            if sr["widget"] is row_widget:
                self._seed_layout.removeWidget(row_widget)
                row_widget.deleteLater()
                del self._seed_rows[i]
                break
        self._update_seed_btn()

    def _update_seed_btn(self):
        self._seed_add_btn.setVisible(len(self._seed_rows) < MAX_SEED_EVENTS)

    def load_project(self, pid):
        self._pid = pid
        project = ProjectRepository().get_by_id(pid) if pid else None
        scenario = project.scenario if project else {}
        self._apply_agents_config(scenario.get("agents_config", {}))
        self._apply_seed_events(scenario.get("seed_events", []))

    def _apply_agents_config(self, agents_config):
        for cd in self._agent_cards:
            cfg = agents_config.get(str(cd["id"]), {})
            tmpl = AgentFactory.get_template(cd["id"])
            stance_val = cfg.get("stance", tmpl["decision_stance"])
            cd["stance"].set_value(stance_val)
            cd["activity"].setValue(int(cfg.get("activity", tmpl["activity"]) * 100))
            cd["influence"].setValue(float(cfg.get("influence", tmpl["influence"])))
            cd["profile"].setPlainText(cfg.get("profile", tmpl["profile"]))

    def _apply_seed_events(self, seed_events):
        while self._seed_rows:
            sr = self._seed_rows.pop()
            self._seed_layout.removeWidget(sr["widget"])
            sr["widget"].deleteLater()
        for event in seed_events:
            self._add_seed_row(event)
        self._update_seed_btn()

    # --- AI 生成行为体配置 ---

    def _ai_generate(self):
        if not self._pid:
            self.log("请先在 Step1 保存供应链场景", is_error=True)
            return
        project = ProjectRepository().get_by_id(self._pid)
        scenario = project.scenario if project else {}
        if not scenario.get("background"):
            self.log("请先在 Step1 填写供应链背景", is_error=True)
            return
        client = build_llm_client()
        if client is None:
            self.log("未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key", is_error=True)
            return
        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("AI 生成中…")
        run_ai_task(
            self,
            lambda: generate_agent_config(client, scenario),
            self._on_ai_config,
            self._on_ai_error,
        )

    def _reset_ai_btn(self):
        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("AI 生成行为体配置")

    def _on_ai_config(self, result):
        self._reset_ai_btn()
        self._apply_agents_config(result.get("agents_config", {}))
        self._apply_seed_events(result.get("seed_events", []))
        self.log("AI 已生成行为体配置与种子事件，请核对后保存")

    def _on_ai_error(self, err):
        self._reset_ai_btn()
        self.log(f"AI 生成失败：{err}", is_error=True)

    def reset(self):
        self._pid = None
        self.load_project(None)

    def _save(self):
        if not self._pid:
            return

        agents_config = {
            str(cd["id"]): {
                "stance": cd["stance"].value(),
                "activity": round(cd["activity"].value() / 100, 2),
                "influence": cd["influence"].value(),
                "profile": cd["profile"].toPlainText().strip(),
            }
            for cd in self._agent_cards
        }

        seed_events = []
        max_cycle = max(app_config.sim.max_rounds, 1)
        for sr in self._seed_rows:
            content = sr["content"].text().strip()
            if not content:
                self.log("请填写所有种子事件的内容", is_error=True)
                return
            # 行的周期上限在创建时确定，保存时按当前设置钳制一次
            cycle = max(1, min(sr["cycle"].value(), max_cycle))
            seed_events.append({"content": content, "cycle": cycle})

        repo = ProjectRepository()
        project = repo.get_by_id(self._pid)
        if not project:
            return
        # update_scenario 为全量替换，先读旧 scenario 再合并写回
        scenario = dict(project.scenario)
        scenario["agents_config"] = agents_config
        scenario["seed_events"] = seed_events
        repo.update_scenario(self._pid, scenario)

        self.agents_saved.emit(self._pid)
