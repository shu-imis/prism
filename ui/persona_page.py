"""行为体性格配置"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import app_config
from core.agent import AGENT_TEMPLATES
from core.agent_factory import AgentFactory
from core.constants import STANCES
from llm.analysis import generate_agent_config
from llm.config import build_llm_client
from services.workspace import WorkspaceService
from ui.ai_worker import run_ai_task_with_button
from ui.save_flow import SaveFlow
from ui.scroll import ChainingTextEdit, SmoothScrollArea
from ui.styles import (
    PAD_MD,
    PAD_SM,
    PAD_XL,
    TEXT_PRIMARY,
    mono_value_qss,
    role_badge_qss,
)
from ui.widgets import (
    Caption,
    Card,
    DangerBtn,
    DecimalInput,
    GhostBtn,
    Input,
    NumberInput,
    SegmentedControl,
    StatusLabel,
    Title,
)

MAX_SEED_EVENTS = 3


class PersonaPage(QWidget):
    agents_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._agent_cards = []
        self._seed_rows = []
        self._form_baseline = None
        self._ws = WorkspaceService()
        self._flow = SaveFlow(self)
        # 终端日志回调：默认空实现，由 ProcessPage 注入覆盖（单独实例化也能用）
        self.log = lambda *args, **kwargs: None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea()

        inner = QWidget()
        self._il = QVBoxLayout(inner)
        self._il.setContentsMargins(PAD_XL, PAD_XL, PAD_XL, PAD_XL)
        self._il.setSpacing(PAD_SM)

        card = Card()
        header = QHBoxLayout()
        header.addWidget(Title("行为体性格配置", 14))
        header.addStretch()
        self._ai_btn = GhostBtn("AI 生成行为体配置")
        self._ai_btn.clicked.connect(self._ai_generate)
        self._ai_status = StatusLabel()
        header.addWidget(self._ai_status)
        header.addWidget(self._ai_btn)
        card.add_layout(header)
        card.add(Caption(
            f"调整 {len(AGENT_TEMPLATES)} 个行为体的决策倾向、活跃度、影响力与角色画像，"
            "观察单条供应链的演化"
        ))
        self._il.addWidget(card)

        for tmpl in AGENT_TEMPLATES:
            self._il.addWidget(self._build_agent_card(tmpl))

        # --- 种子事件 ---
        self._seed_card = Card()
        self._seed_card.add(Title("种子事件", 14))
        self._seed_card.add(Caption(f"在指定周期向供应链注入外部干预（最多 {MAX_SEED_EVENTS} 条）"))
        self._seed_layout = QVBoxLayout()
        self._seed_layout.setSpacing(PAD_SM)
        self._seed_card.add_layout(self._seed_layout)
        self._seed_add_btn = GhostBtn("＋ 添加种子事件")
        self._seed_add_btn.clicked.connect(lambda: self._add_seed_row())
        self._seed_card.add(self._seed_add_btn)
        self._il.addWidget(self._seed_card)

        self._il.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _build_agent_card(self, tmpl):
        card = Card(padding=PAD_MD)

        hdr = QHBoxLayout()
        hdr.addWidget(Title(tmpl["name"], 13))
        role = Caption(tmpl["role"])
        role.setStyleSheet(role_badge_qss())
        hdr.addWidget(role)
        hdr.addStretch()
        card.add_layout(hdr)

        row = QHBoxLayout()
        row.addWidget(QLabel("决策倾向"))
        stance = SegmentedControl(STANCES)
        stance.setValue(tmpl["decision_stance"])
        row.addWidget(stance)

        row.addWidget(QLabel("活跃度"))
        activity = QSlider(Qt.Horizontal)
        activity.setRange(0, 100)
        activity.setValue(int(tmpl["activity"] * 100))
        activity.setFixedWidth(140)
        activity_value = QLabel(f"{activity.value()}%")
        activity_value.setFixedWidth(40)
        activity_value.setStyleSheet(mono_value_qss(12, TEXT_PRIMARY))
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
        profile = ChainingTextEdit()
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
        self._flow.reset()
        project = self._ws.load_project(pid)
        scenario = project.scenario if project else {}
        self._apply_agents_config(scenario.get("agents_config", {}))
        self._apply_seed_events(scenario.get("seed_events", []))
        self._form_baseline = self._collect_config()

    def _apply_agents_config(self, agents_config):
        for cd in self._agent_cards:
            cfg = agents_config.get(str(cd["id"]), {})
            tmpl = AgentFactory.get_template(cd["id"])
            stance_val = cfg.get("stance", tmpl["decision_stance"])
            cd["stance"].setValue(stance_val)
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
        project = self._ws.load_project(self._pid)
        scenario = project.scenario if project else {}
        if not scenario.get("background"):
            self.log("请先在 Step1 填写供应链背景", is_error=True)
            return
        client = build_llm_client()
        if client is None:
            self.log("未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key", is_error=True)
            return
        pid = self._pid
        run_ai_task_with_button(
            self,
            self._ai_btn,
            self._ai_status,
            "AI 生成中…",
            lambda: generate_agent_config(client, scenario),
            lambda result: self._on_ai_config(result, pid),
            self._on_ai_error,
        )

    def _on_ai_config(self, result, pid):
        # 等待期间用户可能已切换项目：pid 不匹配则忽略结果，避免旧数据填进新页面
        if pid != self._pid:
            return
        self._apply_agents_config(result.get("agents_config", {}))
        self._apply_seed_events(result.get("seed_events", []))
        self.log("AI 已生成行为体配置与种子事件，请核对后保存")

    def _on_ai_error(self, err):
        self.log(f"AI 生成失败：{err}", is_error=True)

    def reset(self):
        self._pid = None
        self.load_project(None)

    def save(self):
        """公开保存入口（供工作区导航按钮调用）。"""
        self._save()

    def _collect_config(self):
        """收集当前表单的行为体配置与种子事件。"""
        agents_config = {
            str(cd["id"]): {
                "stance": cd["stance"].value(),
                "activity": round(cd["activity"].value() / 100, 2),
                "influence": cd["influence"].value(),
                "profile": cd["profile"].toPlainText().strip(),
            }
            for cd in self._agent_cards
        }
        max_cycle = max(app_config.sim.max_rounds, 1)
        seed_events = []
        for sr in self._seed_rows:
            # 行的周期上限在创建时确定，收集时按当前设置钳制一次
            cycle = max(1, min(sr["cycle"].value(), max_cycle))
            seed_events.append({"content": sr["content"].text().strip(), "cycle": cycle})
        return agents_config, seed_events

    def has_unsaved_changes(self) -> bool:
        """本步是否有未保存的修改，供导航与状态指示判断。"""
        if self._form_baseline is None:
            return False
        return self._collect_config() != self._form_baseline

    def _save(self):
        if not self._pid:
            return

        agents_config, seed_events = self._collect_config()
        for sr in seed_events:
            if not sr["content"]:
                self.log("请填写所有种子事件的内容", is_error=True)
                return

        project = self._ws.load_project(self._pid)
        if not project:
            # 项目已在首页被删除：不静默吞掉，提示用户重新创建
            self.log("项目已被删除，请回到首页重新创建或打开其他项目", is_error=True)
            return
        fields = {"agents_config": agents_config, "seed_events": seed_events}
        # 与本步载入时的表单比对：识别用户真实编辑，不受库中存储格式影响
        outcome = self._flow.resolve(
            changed=(agents_config, seed_events) != self._form_baseline,
            status=project.status,
            payload=fields,
            confirm_text="行为体或种子事件已变更，该项目的全部仿真轮次、断点与报告将被清除，无法恢复。",
        )
        if outcome == "discard":
            # 上次取消保存后未再编辑：确认放弃修改，表单恢复后直接继续
            self.load_project(self._pid)
            self.log("已放弃未保存的修改")
            self.agents_saved.emit(self._pid)
            return
        if outcome == "defer":
            self.log("本步修改未保存；再点「下一步」将放弃修改并继续")
            return
        if outcome != "skip":
            self._ws.commit_save(
                self._pid, fields, invalidate=(outcome == "commit_invalidate")
            )

        self._form_baseline = (agents_config, seed_events)
        self.log(f"项目已保存（#{self._pid}）")
        self.agents_saved.emit(self._pid)
