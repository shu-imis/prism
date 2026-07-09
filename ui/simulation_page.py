"""仿真运行页 —— 真实 LLM 桌面 demo。"""
from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import DB_PATH, app_config
from core.agent_factory import AgentFactory
from core.scenario_parser import Scenario, ScenarioParser
from core.simulation_engine import SimStatus, SimulationEngine
from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRoundRepository,
    StrategyRepository,
    CheckpointRepository,
    KnowledgeRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.exporter import ReportExporter
from report.generator import ReportGenerator
from ui.styles import TEXT_SECONDARY, TEXT_TERTIARY
from ui.widgets import (
    BodyLabel,
    CaptionLabel,
    PrismCard,
    PrismDangerButton,
    PrismLineEdit,
    PrismPrimaryButton,
    PrismSecondaryButton,
    SectionTitle,
)


DEMO_SCENARIO = {
    "title": "连锁茶饮食品安全争议",
    "industry": "餐饮 / 新消费",
    "background": (
        "某连锁茶饮品牌被消费者发布视频质疑门店后厨卫生管理不规范，"
        "相关话题开始在社交平台扩散。部分媒体已经联系企业求证，"
        "监管部门尚未正式介入。"
    ),
    "company_statement": "企业已关注相关反馈，正在核查涉事门店情况。",
    "initial_heat": 52.0,
    "baseline_sentiment": -0.35,
}


DEFAULT_STRATEGIES = [
    {
        "name": "快速道歉与透明整改",
        "statement": (
            "我们向消费者诚恳致歉，已暂停涉事门店营业并启动第三方卫生检查。"
            "今晚 20 点前公布初步核查结果，并同步全部整改措施。"
        ),
        "release_hour": 4,
    },
    {
        "name": "先核查再回应",
        "statement": (
            "我们已启动内部核查，将在事实确认后向公众说明情况。"
            "在调查完成前，请大家以官方信息为准，避免传播未经证实内容。"
        ),
        "release_hour": 8,
    },
]


PROVIDER_PRESETS = [
    {
        "label": "OpenAI",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "",
        "model": app_config.llm.default_model,
    },
    {
        "label": "Anthropic",
        "protocol": LLMProvider.ANTHROPIC.value,
        "base_url": "",
        "model": "claude-3-5-haiku-latest",
    },
    {
        "label": "DeepSeek",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    {
        "label": "通义千问 DashScope",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    {
        "label": "Moonshot Kimi",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    {
        "label": "智谱 GLM",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    {
        "label": "自定义",
        "protocol": LLMProvider.OPENAI.value,
        "base_url": "",
        "model": "",
    },
]


class DemoSimulationWorker(QThread):
    """后台运行真实 LLM 仿真，避免阻塞 UI。"""

    progress = Signal(int, int, str)
    round_completed = Signal(dict)
    demo_completed = Signal(object, object)
    failed = Signal(str)
    stopped = Signal(str)

    def __init__(
        self,
        *,
        protocol: str,
        api_key: str,
        base_url: str,
        model: str,
        max_rounds: int,
        strategy_a_statement: str,
        strategy_b_statement: str,
        project_id: int | None = None,
        checkpoint_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.protocol = protocol
        self.api_key = api_key.strip()
        self.base_url = base_url.strip()
        self.model = model.strip()
        self.max_rounds = max_rounds
        self.strategy_a_statement = strategy_a_statement.strip()
        self.strategy_b_statement = strategy_b_statement.strip()
        self.project_id = project_id
        self.checkpoint_id = checkpoint_id
        self._engine: SimulationEngine | None = None

    def pause(self) -> None:
        if self._engine:
            self._engine.pause()

    def resume(self) -> None:
        if self._engine:
            self._engine.resume()

    def abort(self) -> None:
        if self._engine:
            self._engine.abort()

    def run(self) -> None:
        try:
            db = Database(DB_PATH)
            try:
                db.migrate()
                project_repo = ProjectRepository(db)
                strategy_repo = StrategyRepository(db)
                round_repo = SimulationRoundRepository(db)
                report_repo = ReportRepository(db)
                checkpoint_repo = CheckpointRepository(db)
                knowledge_repo = KnowledgeRepository(db)

                resume_checkpoint = checkpoint_repo.get_by_id(self.checkpoint_id) if self.checkpoint_id else None
                if resume_checkpoint:
                    payload = resume_checkpoint.engine_state
                    project = project_repo.get_by_id(resume_checkpoint.project_id)
                    if project is None:
                        raise RuntimeError("检查点对应的项目不存在，无法恢复。")
                    scenario = Scenario.from_dict(payload.get("scenario") or project.scenario)
                    strategy_records = strategy_repo.list_by_project(project.id)
                    strategies = [
                        {
                            "name": record.name,
                            "statement": record.statement,
                            "release_hour": record.release_hour,
                        }
                        for record in strategy_records
                    ]
                    max_rounds = int(payload.get("max_rounds", self.max_rounds))
                elif self.project_id is not None:
                    project = project_repo.get_by_id(self.project_id)
                    if project is None:
                        raise RuntimeError("项目不存在，无法启动仿真。")
                    scenario = Scenario.from_dict(project.scenario)
                    strategy_records = strategy_repo.list_by_project(project.id)
                    if len(strategy_records) < 2:
                        raise RuntimeError("至少需要配置 2 个策略。")
                    strategies = [
                        {
                            "name": record.name,
                            "statement": record.statement,
                            "release_hour": record.release_hour,
                        }
                        for record in strategy_records
                    ]
                    max_rounds = self.max_rounds
                else:
                    scenario = ScenarioParser.parse(**DEMO_SCENARIO)
                    strategies = [
                        {
                            **DEFAULT_STRATEGIES[0],
                            "statement": self.strategy_a_statement or DEFAULT_STRATEGIES[0]["statement"],
                        },
                        {
                            **DEFAULT_STRATEGIES[1],
                            "statement": self.strategy_b_statement or DEFAULT_STRATEGIES[1]["statement"],
                        },
                    ]
                    project = project_repo.create(scenario.title, scenario.to_dict())
                    strategy_records = [
                        strategy_repo.create(
                            project.id,
                            name=strategy["name"],
                            statement=strategy["statement"],
                            release_hour=int(strategy["release_hour"]),
                        )
                        for strategy in strategies
                    ]
                    max_rounds = self.max_rounds

                llm_client = self._build_llm_client()
                engine = SimulationEngine(llm_client=llm_client, random_seed=42)
                self._engine = engine
                engine.configure(
                    AgentFactory.create_all(),
                    scenario,
                    strategies,
                    max_rounds=max_rounds,
                    project_id=project.id,
                    strategy_records=strategy_records,
                    round_repository=round_repo,
                    checkpoint_repository=checkpoint_repo,
                    knowledge_repository=knowledge_repo,
                    resume_checkpoint=resume_checkpoint,
                )
                engine.set_progress_callback(lambda current, total, message: self.progress.emit(current, total, message))
                engine.set_round_callback(self._emit_round)
                results = engine.run()
                if engine.state.status == SimStatus.ABORTED:
                    self.stopped.emit("推演已中止，当前进度已保存为检查点。")
                    return

                generator = ReportGenerator(project_name=project.name, scenario_background=scenario.background)
                for strategy, rounds in zip(strategies, results):
                    generator.add_strategy_result(strategy["name"], strategy["statement"], rounds)
                report = generator.generate()
                report_repo.save(
                    project_id=project.id,
                    title=f"{project.name} 推演报告",
                    markdown=ReportExporter.to_markdown(report),
                    html=ReportExporter.export_html(report),
                    summary=report.to_dict(),
                )
            finally:
                self._engine = None
                db.close()
            self.demo_completed.emit(report, results)
        except Exception as exc:  # noqa: BLE001 - UI 需要展示第三方 SDK 错误
            self.failed.emit(str(exc))

    def _build_llm_client(self) -> LLMClient:
        preferred = LLMProvider(self.protocol)
        if self.base_url or self.api_key:
            api_key = self.api_key or os.getenv("LLM_API_KEY")
            if not api_key:
                raise RuntimeError("使用自定义 URL 或第三方兼容接口时，请填写 API Key，或设置 LLM_API_KEY。")
            default_model = "claude-3-5-haiku-latest" if preferred == LLMProvider.ANTHROPIC else app_config.llm.default_model
            if self.base_url and not self.model:
                raise RuntimeError("请填写模型名称。")
            model = self.model or default_model
            return LLMClient(
                providers=[
                    ProviderSettings(
                        provider=preferred,
                        model=model,
                        api_key=api_key,
                        base_url=self.base_url or None,
                    )
                ]
            )

        client = LLMClient.from_env(prefer=preferred)
        if self.model:
            client.providers = [
                ProviderSettings(provider.provider, self.model, provider.api_key, provider.base_url)
                for provider in client.providers
            ]
        return client

    def _emit_round(self, strategy_index: int, strategy: dict[str, Any], state, messages: list[dict[str, Any]]) -> None:
        self.round_completed.emit(
            {
                "strategy_index": strategy_index,
                "strategy_name": strategy.get("name", f"策略 {strategy_index + 1}"),
                "round": state.round,
                "simulated_hour": state.simulated_hour,
                "heat": state.heat,
                "sentiment": state.sentiment,
                "support_rate": state.support_rate,
                "events": [event.description for event in state.key_events],
                "messages": messages,
            }
        )


class SimulationPage(QWidget):
    """多智能体仿真运行 demo。"""

    demo_completed = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: DemoSimulationWorker | None = None
        self._checkpoint_id: int | None = None
        self._project_id: int | None = None
        self._build_ui()
        self._refresh_checkpoint_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(18)

        title = SectionTitle("真实 LLM 舆论推演 Demo")
        intro = BodyLabel(
            "使用预置危机场景和两套回应策略，调用真实 LLM 兼容接口生成 Agent 反应。"
            "可选择常见厂商预设，也可自定义 Base URL、协议格式、API Key 和模型。"
        )
        layout.addWidget(title)
        layout.addWidget(intro)

        config_card = PrismCard()
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.provider_combo = QComboBox()
        for preset in PROVIDER_PRESETS:
            self.provider_combo.addItem(preset["label"], preset)
        self.provider_combo.currentIndexChanged.connect(self._apply_provider_preset)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("OpenAI-compatible", LLMProvider.OPENAI.value)
        self.protocol_combo.addItem("Anthropic-compatible", LLMProvider.ANTHROPIC.value)

        self.api_key_input = PrismLineEdit("留空则读取 .env / 环境变量")
        self.api_key_input.setEchoMode(QLineEdit.Password)

        self.base_url_input = PrismLineEdit("官方厂商可留空；第三方/自定义填写兼容接口 URL")

        self.model_input = PrismLineEdit()
        self.model_input.setText(app_config.llm.default_model)

        self.rounds_input = QSpinBox()
        self.rounds_input.setRange(8, 12)
        self.rounds_input.setValue(8)

        grid.addWidget(QLabel("厂商预设"), 0, 0)
        grid.addWidget(self.provider_combo, 0, 1)
        grid.addWidget(QLabel("协议格式"), 0, 2)
        grid.addWidget(self.protocol_combo, 0, 3)
        grid.addWidget(QLabel("Base URL"), 1, 0)
        grid.addWidget(self.base_url_input, 1, 1, 1, 3)
        grid.addWidget(QLabel("API Key"), 2, 0)
        grid.addWidget(self.api_key_input, 2, 1)
        grid.addWidget(QLabel("模型"), 2, 2)
        grid.addWidget(self.model_input, 2, 3)
        grid.addWidget(QLabel("轮数"), 3, 0)
        grid.addWidget(self.rounds_input, 3, 1)
        config_card.addLayout(grid)
        layout.addWidget(config_card)

        scenario_card = PrismCard()
        scenario_card.addWidget(SectionTitle(DEMO_SCENARIO["title"]))
        scenario_card.addWidget(
            BodyLabel(
                f"{DEMO_SCENARIO['industry']} · 初始热度 {DEMO_SCENARIO['initial_heat']:.0f} / "
                f"情绪 {DEMO_SCENARIO['baseline_sentiment']:.2f}\n{DEMO_SCENARIO['background']}"
            )
        )
        layout.addWidget(scenario_card)

        strategy_card = PrismCard()
        strategy_card.addWidget(SectionTitle("回应策略"))
        strategy_grid = QGridLayout()
        strategy_grid.setHorizontalSpacing(14)
        strategy_grid.setVerticalSpacing(8)
        self.strategy_a_input = QPlainTextEdit(DEFAULT_STRATEGIES[0]["statement"])
        self.strategy_b_input = QPlainTextEdit(DEFAULT_STRATEGIES[1]["statement"])
        self.strategy_a_input.setMinimumHeight(92)
        self.strategy_b_input.setMinimumHeight(92)
        strategy_grid.addWidget(QLabel("策略 A · 快速道歉与透明整改"), 0, 0)
        strategy_grid.addWidget(QLabel("策略 B · 先核查再回应"), 0, 1)
        strategy_grid.addWidget(self.strategy_a_input, 1, 0)
        strategy_grid.addWidget(self.strategy_b_input, 1, 1)
        strategy_card.addLayout(strategy_grid)
        layout.addWidget(strategy_card)

        control_row = QHBoxLayout()
        self.start_button = PrismPrimaryButton("启动真实 LLM 推演")
        self.start_button.clicked.connect(lambda: self._start_demo())
        self.resume_checkpoint_button = PrismSecondaryButton("恢复上次推演")
        self.resume_checkpoint_button.clicked.connect(self._resume_checkpoint)
        self.pause_button = PrismSecondaryButton("暂停")
        self.pause_button.clicked.connect(self._pause_demo)
        self.continue_button = PrismSecondaryButton("继续")
        self.continue_button.clicked.connect(self._continue_demo)
        self.abort_button = PrismDangerButton("中止")
        self.abort_button.clicked.connect(self._abort_demo)
        self.status_label = CaptionLabel("准备就绪")
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.resume_checkpoint_button)
        control_row.addWidget(self.pause_button)
        control_row.addWidget(self.continue_button)
        control_row.addWidget(self.abort_button)
        control_row.addWidget(self.status_label, 1)
        layout.addLayout(control_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        metrics_card = PrismCard()
        metrics_card.addWidget(SectionTitle("实时指标"))
        self.metrics_label = BodyLabel("尚未开始。")
        metrics_card.addWidget(self.metrics_label)
        layout.addWidget(metrics_card)

        log_card = PrismCard()
        log_card.addWidget(SectionTitle("Agent 发言流"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(220)
        log_card.addWidget(self.log_view)
        layout.addWidget(log_card)
        layout.addStretch()
        self.pause_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.abort_button.setEnabled(False)

        self._apply_provider_preset()

    def _apply_provider_preset(self) -> None:
        preset = self.provider_combo.currentData()
        if not preset:
            return
        protocol = preset.get("protocol", LLMProvider.OPENAI.value)
        protocol_index = self.protocol_combo.findData(protocol)
        if protocol_index >= 0:
            self.protocol_combo.setCurrentIndex(protocol_index)
        self.base_url_input.setText(preset.get("base_url", ""))
        self.model_input.setText(preset.get("model", ""))

    def _start_demo(self, checkpoint_id: int | None = None) -> None:
        self.start_button.setEnabled(False)
        self.resume_checkpoint_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.continue_button.setEnabled(True)
        self.abort_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self.status_label.setText("正在恢复推演..." if checkpoint_id else "正在调用真实 LLM，请稍候...")
        self.metrics_label.setText("等待第一轮结果。")

        self._worker = DemoSimulationWorker(
            protocol=self.protocol_combo.currentData(),
            api_key=self.api_key_input.text(),
            base_url=self.base_url_input.text(),
            model=self.model_input.text(),
            max_rounds=self.rounds_input.value(),
            strategy_a_statement=self.strategy_a_input.toPlainText(),
            strategy_b_statement=self.strategy_b_input.toPlainText(),
            project_id=None if checkpoint_id else self._project_id,
            checkpoint_id=checkpoint_id,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.round_completed.connect(self._on_round_completed)
        self._worker.demo_completed.connect(self._on_demo_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.stopped.connect(self._on_stopped)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _resume_checkpoint(self) -> None:
        self._refresh_checkpoint_status()
        if self._checkpoint_id is None:
            QMessageBox.information(self, "Prism", "没有找到可恢复的检查点。")
            return
        self._start_demo(checkpoint_id=self._checkpoint_id)

    def _pause_demo(self) -> None:
        if self._worker:
            self._worker.pause()
            self.status_label.setText("已请求暂停，当前 LLM 调用完成后生效。")

    def _continue_demo(self) -> None:
        if self._worker:
            self._worker.resume()
            self.status_label.setText("继续推演。")

    def _abort_demo(self) -> None:
        if self._worker:
            self._worker.abort()
            self.status_label.setText("正在中止，当前进度会保存为检查点。")

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_round_completed(self, payload: dict[str, Any]) -> None:
        self.metrics_label.setText(
            "策略：{strategy}｜第 {round} 轮｜模拟 {hour} 小时｜热度 {heat:.1f}｜情绪 {sentiment:.2f}｜支持率 {support:.1%}".format(
                strategy=payload["strategy_name"],
                round=payload["round"],
                hour=payload["simulated_hour"],
                heat=payload["heat"],
                sentiment=payload["sentiment"],
                support=payload["support_rate"],
            )
        )
        events = "；".join(payload["events"]) if payload["events"] else "无关键事件"
        self._append_log(f"\n[{payload['strategy_name']} · 第 {payload['round']} 轮] {events}")
        messages = payload["messages"]
        if not messages:
            self._append_log("本轮无 Agent 激活。")
        for message in messages:
            metrics = message.get("metrics", {})
            if metrics.get("skipped"):
                error = metrics.get("error_message") or metrics.get("warning") or "未知原因"
                self._append_log(f"{message.get('agent_name', 'Agent')}：已跳过｜{error}")
                continue
            content = message.get("content") or "未发言"
            self._append_log(f"{message.get('agent_name', 'Agent')}：{content}")

    def _on_demo_completed(self, report, results) -> None:
        self.status_label.setText("推演完成，正在展示结果。")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self._append_log("\n推演完成，报告已生成。")
        self._refresh_checkpoint_status()
        self.demo_completed.emit(report, results)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("推演失败")
        self._append_log(f"\n错误：{message}")
        self._refresh_checkpoint_status()
        QMessageBox.critical(self, "Prism 推演失败", message)

    def _on_stopped(self, message: str) -> None:
        self.status_label.setText("推演已中止")
        self._append_log(f"\n{message}")
        self._refresh_checkpoint_status()

    def _on_worker_finished(self) -> None:
        self._worker = None
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.abort_button.setEnabled(False)
        self.resume_checkpoint_button.setEnabled(self._checkpoint_id is not None)

    def _append_log(self, text: str) -> None:
        self.log_view.append(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def load_project(self, project_id: int) -> None:
        project = ProjectRepository().get_by_id(project_id)
        if project is None:
            return
        strategies = StrategyRepository().list_by_project(project.id)
        self._project_id = project.id
        self.status_label.setText(f"已加载项目：{project.name}（{len(strategies)} 个策略）")
        self.metrics_label.setText("点击启动后将使用当前项目的事件和策略运行仿真。")
        if len(strategies) >= 2:
            self.strategy_a_input.setPlainText(strategies[0].statement)
            self.strategy_b_input.setPlainText(strategies[1].statement)

    def _refresh_checkpoint_status(self) -> None:
        db = Database(DB_PATH)
        try:
            db.migrate()
            checkpoints = CheckpointRepository(db).list_unfinished(limit=1)
        finally:
            db.close()
        checkpoint = checkpoints[0] if checkpoints else None
        self._checkpoint_id = checkpoint.id if checkpoint else None
        if hasattr(self, "resume_checkpoint_button"):
            self.resume_checkpoint_button.setEnabled(self._checkpoint_id is not None and self._worker is None)
        if checkpoint:
            self.status_label.setText(f"检测到可恢复检查点：项目 {checkpoint.project_id}，第 {checkpoint.last_round} 轮。")
