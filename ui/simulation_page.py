"""仿真运行"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_config, DB_PATH
from core.agent_factory import AgentFactory
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from db.database import Database
from db.models import CheckpointRepository, ProjectRepository, SimulationRoundRepository, StrategyRepository
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.generator import ReportGenerator
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    GhostBtn,
    Input,
    PrimaryBtn,
    ProgressBar,
    SecondaryBtn,
    Title,
)

PRESETS = [
    {"label": "OpenAI", "proto": "openai", "url": "https://api.openai.com/v1", "model": "gpt-5.6-sol"},
    {"label": "Anthropic", "proto": "anthropic", "url": "https://api.anthropic.com", "model": "claude-fable-5"},
    {"label": "DeepSeek", "proto": "openai", "url": "https://api.deepseek.com", "model": "deepseek-v4-pro"},
    {"label": "通义千问", "proto": "openai", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen3.7-max"},
    {"label": "Kimi", "proto": "openai", "url": "https://api.moonshot.cn/v1", "model": "kimi-k2.7-code"},
    {"label": "智谱", "proto": "openai", "url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-5.2"},
    {"label": "自定义", "proto": "openai", "url": "", "model": ""},
]


class SimWorker(QThread):
    progress = Signal(int, int, str)
    round_done = Signal(dict)
    finished = Signal(object, list)
    failed = Signal(str)
    recoverable = Signal(str)      # 中断但可恢复

    def __init__(self, pid, proto, key, url, model, rounds):
        super().__init__()
        self.pid = pid
        self.proto = proto
        self.key = key
        self.url = url
        self.model = model
        self.rounds = rounds
        self._paused = False
        self._checkpoint = None

    def set_checkpoint(self, checkpoint):
        self._checkpoint = checkpoint

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def run(self):
        try:
            db = Database(DB_PATH)
            if self.proto == "openai":
                ps = ProviderSettings(
                    LLMProvider.OPENAI, self.model,
                    self.key or os.getenv("OPENAI_API_KEY"),
                    self.url or os.getenv("LLM_BASE_URL"),
                )
            else:
                ps = ProviderSettings(
                    LLMProvider.ANTHROPIC, self.model,
                    self.key or os.getenv("ANTHROPIC_API_KEY"),
                    self.url,
                )

            llm = LLMClient(providers=[ps], max_retries=1)
            proj = ProjectRepository(db).get_by_id(self.pid)
            sc = ScenarioParser().parse(**proj.scenario) if proj else None
            sl = StrategyRepository(db).list_by_project(self.pid)
            strategies = [
                {
                    "name": s.name,
                    "actor": s.actor,
                    "decision": s.decision,
                    "release_cycle": s.release_cycle,
                    "parameters": s.parameters,
                }
                for s in sl
            ]
            strategy_records = list(sl)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)

            agents = AgentFactory.create_all()
            engine = SimulationEngine(llm)
            engine.configure(
                agents, sc, strategies,
                max_rounds=self.rounds,
                project_id=self.pid,
                strategy_records=strategy_records,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=self._checkpoint,
            )
            engine.set_progress_callback(
                lambda c, t, m: self.progress.emit(c, t, m)
            )
            engine.set_round_callback(
                lambda si, strategy, state, messages: (
                    None if self._paused else self.round_done.emit({
                        "round": state.round,
                        "inventory": state.inventory_level,
                        "cost": state.cost_index,
                        "delay": state.delivery_delay,
                        "service": state.service_level,
                        "margin": state.profit_margin,
                        "resilience": state.resilience_score,
                        "messages": messages,
                    })
                )
            )

            results = engine.run()
            gen = ReportGenerator(
                proj.name if proj else "",
                sc.background if sc else "",
            )
            for si, sr in enumerate(results):
                nm = strategies[si]["name"] if si < len(strategies) else f"方案{si + 1}"
                dc = strategies[si]["decision"] if si < len(strategies) else ""
                gen.add_strategy_result(nm, dc, sr)

            self.finished.emit(gen.generate(), results)
        except SimulationRecoverableError as e:
            self.recoverable.emit(str(e))
        except Exception as e:
            self.failed.emit(str(e))


class SimulationPage(QWidget):
    simulation_completed = Signal(object, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._running = False
        self._worker = None
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
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(PAD_SM)

        # --- LLM 配置 ---
        cfg = Card()
        cfg.add(Title("LLM 配置", 13))

        self._provider_index = 0
        provider_row = QHBoxLayout()
        provider_row.setSpacing(0)

        self._prov_minus = QPushButton("<")
        self._prov_minus.setFixedSize(BTN_H, BTN_H)
        self._prov_minus.setCursor(Qt.PointingHandCursor)
        self._prov_minus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-right:none;font-size:13px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._prov_minus.clicked.connect(self._prev_provider)

        self._provider_label = QLabel(PRESETS[0]["label"])
        self._provider_label.setFixedHeight(BTN_H)
        self._provider_label.setAlignment(Qt.AlignCenter)
        self._provider_label.setStyleSheet(
            f"QLabel{{background:{BG_INPUT};border:1px solid {BORDER};border-left:none;border-right:none;"
            "font-family:'Space Grotesk','Noto Sans SC';"
            f"font-size:13px;font-weight:600;color:{TEXT_PRIMARY};}}"
        )

        self._prov_plus = QPushButton(">")
        self._prov_plus.setFixedSize(BTN_H, BTN_H)
        self._prov_plus.setCursor(Qt.PointingHandCursor)
        self._prov_plus.setStyleSheet(
            f"QPushButton{{background:{BG_SURFACE};border:1px solid {BORDER};border-left:none;font-size:13px;color:{TEXT_PRIMARY};}}"
            f"QPushButton:hover{{background:{BG_HOVER};}}"
        )
        self._prov_plus.clicked.connect(self._next_provider)

        provider_row.addWidget(self._prov_minus)
        provider_row.addWidget(self._provider_label, 1)
        provider_row.addWidget(self._prov_plus)
        provider_row.addStretch()
        cfg.add_layout(provider_row)

        self._key = Input("API Key")
        self._key.setEchoMode(QLineEdit.Password)
        self._url = Input("Base URL")
        self._model = Input()
        self._model.setText(app_config.llm.default_model)

        self._config_widget = QWidget()
        cv = self._config_widget
        cl = QVBoxLayout(cv)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("API Key"))
        cl.addWidget(self._key)
        cl.addWidget(QLabel("Base URL"))
        cl.addWidget(self._url)
        cl.addWidget(QLabel("模型"))
        cl.addWidget(self._model)
        cfg.add(cv)

        self._toggle_btn = GhostBtn("收起 ▲")
        self._toggle_btn.clicked.connect(self._toggle_config)
        cfg.add(self._toggle_btn)
        il.addWidget(cfg)

        # --- 指标卡 ---
        mr = QHBoxLayout()
        mr.setSpacing(PAD_SM)
        self._mv = {}
        for lb in ["库存", "成本", "服务水平", "利润率", "交付延迟"]:
            c = Card(padding=PAD_SM)
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            v = QLabel("—")
            v.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:16px;"
                f"font-weight:700;color:{TEXT_PRIMARY};"
            )
            c.add(v)
            c.add(Caption(lb))
            self._mv[lb] = v
            mr.addWidget(c)
        il.addLayout(mr)

        self._bar = ProgressBar()
        il.addWidget(self._bar)

        self._st = Caption("")
        self._st.setVisible(False)
        il.addWidget(self._st)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._log.setStyleSheet(
            f"QTextEdit{{background:{BG_INPUT};border:1px solid {BORDER};font-size:12px;}}"
        )
        il.addWidget(self._log, 1)

        br = QHBoxLayout()
        self._start = PrimaryBtn("▶ 启动仿真")
        self._start.clicked.connect(self._toggle)
        br.addWidget(self._start)
        rst = SecondaryBtn("↺ 重置")
        rst.clicked.connect(self._reset)
        br.addWidget(rst)
        br.addStretch()
        il.addLayout(br)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _prev_provider(self):
        self._provider_index = (self._provider_index - 1) % len(PRESETS)
        self._update_provider()

    def _next_provider(self):
        self._provider_index = (self._provider_index + 1) % len(PRESETS)
        self._update_provider()

    def _update_provider(self):
        p = PRESETS[self._provider_index]
        self._provider_label.setText(p["label"])
        self._url.setText(p.get("url", ""))
        self._model.setText(p.get("model", ""))

    def _toggle_config(self):
        cv = self._config_widget
        visible = not cv.isVisible()
        cv.setVisible(visible)
        self._toggle_btn.setText("收起 ▲" if visible else "展开 ▼")

    def load_project(self, pid):
        self._pid = pid
        self._reset()

    def reset_for_new_project(self):
        self._pid = None
        self._reset()

    def _toggle(self):
        if self._running:
            if self._worker:
                self._worker.pause()
            self._running = False
            self._start.setText("▶ 继续")
            return

        p = PRESETS[self._provider_index]
        self._worker = SimWorker(
            self._pid,
            p.get("proto", "openai"),
            self._key.text(),
            self._url.text(),
            self._model.text(),
            app_config.sim.max_rounds,
        )
        if self._pid:
            db = Database()
            cp_repo = CheckpointRepository(db)
            checkpoint = cp_repo.latest_for_project(self._pid)
            if checkpoint:
                self._worker.set_checkpoint(checkpoint)
                self.log("检测到检查点，从断点恢复", is_error=False)
        self._worker.progress.connect(self._on_progress)
        self._worker.round_done.connect(self._on_round)
        self._worker.finished.connect(
            lambda r, res: (
                setattr(self, "_running", False),
                self._bar.setValue(100),
                self._start.setText("✓ 完成"),
                self._start.setEnabled(False),
                self.simulation_completed.emit(r, res),
            )
        )
        self._worker.failed.connect(
            lambda m: (
                setattr(self, "_running", False),
                self.log(m, is_error=True),
                self._start.setText("▶ 重试"),
                self._start.setEnabled(True),
            )
        )
        self._worker.recoverable.connect(
            lambda m: (
                setattr(self, "_running", False),
                self.log(m, is_error=True),
                self._start.setText("↺ 恢复"),
                self._start.setEnabled(True),
            )
        )

        self._running = True
        self._start.setText("⏸ 暂停")
        self._worker.start()

    def _on_progress(self, current, total, message):
        if total:
            self._bar.setValue(int(current / total * 100))
        self._st.setText(message)
        self._st.setVisible(bool(message))

    def _on_round(self, p):
        inv = p.get("inventory", 0)
        cost = p.get("cost", 0)
        svc = p.get("service", 0)
        margin = p.get("margin", 0)
        delay = p.get("delay", 0)
        r = p.get("round", 0)
        messages = p.get("messages", [])

        self._mv["库存"].setText(f"{inv:.1f}")
        self._mv["成本"].setText(f"{cost:.1f}")
        self._mv["服务水平"].setText(f"{svc:.0%}")
        self._mv["利润率"].setText(f"{margin:+.1%}")
        self._mv["交付延迟"].setText(f"{delay:.1f}")

        self._log.append(
            f"  >  [周期 {r}]  库存 {inv:.0f}  成本 {cost:.0f}  "
            f"服务 {svc:.0%}  利润 {margin:+.1%}"
        )

        for msg in messages:
            agent_name = msg.get("agent_name", "未知行为体")
            skipped = msg.get("metrics", {}).get("skipped", False)
            if skipped:
                error = msg.get("metrics", {}).get("error_message", "")
                self._log.append(f"    ×  {agent_name}: {error[:80]}")
            else:
                content = msg.get("content", "")
                if content:
                    self._log.append(f"    ↳  {agent_name}: {content}")

    def _reset(self):
        self._running = False
        self._bar.setValue(0)
        self._st.setText("")
        self._log.clear()
        self._start.setText("▶ 启动仿真")
        self._start.setEnabled(True)
        for v in self._mv.values():
            v.setText("—")
