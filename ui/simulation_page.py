"""仿真运行"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_config
from core.agent_factory import AgentFactory
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine
from db.database import Database
from db.models import ProjectRepository, StrategyRepository
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.generator import ReportGenerator
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    GhostBtn,
    Input,
    PrimaryBtn,
    SecondaryBtn,
    Title,
)

PRESETS = [
    {"label": "OpenAI", "proto": "openai", "url": "", "model": app_config.llm.default_model},
    {"label": "Anthropic", "proto": "anthropic", "url": "", "model": "claude-3-5-haiku-latest"},
    {"label": "DeepSeek", "proto": "openai", "url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"label": "通义千问", "proto": "openai", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    {"label": "Kimi", "proto": "openai", "url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    {"label": "智谱", "proto": "openai", "url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    {"label": "自定义", "proto": "openai", "url": "", "model": ""},
]


class SimWorker(QThread):
    progress = Signal(int, int, str)
    round_done = Signal(dict)
    finished = Signal(object, list)
    failed = Signal(str)

    def __init__(self, pid, proto, key, url, model, rounds):
        super().__init__()
        self.pid = pid
        self.proto = proto
        self.key = key
        self.url = url
        self.model = model
        self.rounds = rounds
        self._paused = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def run(self):
        try:
            db = Database()
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

            agents = AgentFactory.create_all()
            engine = SimulationEngine(llm)
            engine.configure(agents, sc, strategies, max_rounds=self.rounds)
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
        il.setContentsMargins(0, 0, PAD_XL, 0)
        il.setSpacing(PAD_SM)

        # --- LLM 配置 ---
        cfg = Card()
        cfg.add(Title("LLM 配置", 13))

        self._prov = QComboBox()
        for p in PRESETS:
            self._prov.addItem(p["label"], p)
        self._prov.currentIndexChanged.connect(self._apply_preset)

        self._key = Input("API Key")
        self._key.setEchoMode(QLineEdit.Password)
        self._url = Input("Base URL")
        self._model = Input()
        self._model.setText(app_config.llm.default_model)

        cv = QWidget()
        cl = QVBoxLayout(cv)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("厂商"))
        cl.addWidget(self._prov)
        cl.addWidget(QLabel("API Key"))
        cl.addWidget(self._key)
        cl.addWidget(QLabel("Base URL"))
        cl.addWidget(self._url)
        cl.addWidget(QLabel("模型"))
        cl.addWidget(self._model)
        cfg.add(cv)

        tb = GhostBtn("收起 ▲")
        tb.clicked.connect(lambda: cv.setVisible(not cv.isVisible()))
        cfg.add(tb)
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

        self._bar = QProgressBar()
        il.addWidget(self._bar)

        self._st = Caption("")
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

        self._err = QLabel("")
        self._err.setStyleSheet(f"color:{COLOR_RED};font-size:12px;")
        self._err.setVisible(False)
        il.addWidget(self._err)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def load_project(self, pid):
        self._pid = pid
        self._reset()

    def reset_for_new_project(self):
        self._pid = None
        self._reset()

    def _apply_preset(self):
        p = self._prov.currentData()
        if p:
            self._url.setText(p.get("url", ""))
            self._model.setText(p.get("model", ""))

    def _toggle(self):
        if self._running:
            if self._worker:
                self._worker.pause()
            self._running = False
            self._start.setText("▶ 继续")
            return

        p = self._prov.currentData() or {}
        self._worker = SimWorker(
            self._pid,
            p.get("proto", "openai"),
            self._key.text(),
            self._url.text(),
            self._model.text(),
            app_config.sim.max_rounds,
        )
        self._worker.progress.connect(
            lambda c, t, m: (
                self._bar.setValue(int(c / t * 100)),
                self._st.setText(m),
            )
        )
        self._worker.round_done.connect(self._on_round)
        self._worker.finished.connect(
            lambda r, res: (
                setattr(self, "_running", False),
                self._start.setText("✓ 完成"),
                self._start.setEnabled(False),
                self.simulation_completed.emit(r, res),
            )
        )
        self._worker.failed.connect(
            lambda m: (
                setattr(self, "_running", False),
                self._err.setText(m),
                self._err.setVisible(True),
                self._start.setText("▶ 重试"),
                self._start.setEnabled(True),
            )
        )

        self._running = True
        self._start.setText("⏸ 暂停")
        self._worker.start()

    def _on_round(self, p):
        inv = p.get("inventory", 0)
        cost = p.get("cost", 0)
        svc = p.get("service", 0)
        margin = p.get("margin", 0)
        delay = p.get("delay", 0)
        r = p.get("round", 0)

        self._mv["库存"].setText(f"{inv:.1f}")
        self._mv["成本"].setText(f"{cost:.1f}")
        self._mv["服务水平"].setText(f"{svc:.0%}")
        self._mv["利润率"].setText(f"{margin:+.1%}")
        self._mv["交付延迟"].setText(f"{delay:.1f}")

        self._log.append(
            f"[周期{r}] 库存{inv:.0f} 成本{cost:.0f} "
            f"服务{svc:.0%} 利润{margin:+.1%}"
        )

    def _reset(self):
        self._running = False
        self._bar.setValue(0)
        self._st.setText("")
        self._log.clear()
        self._err.setVisible(False)
        self._start.setText("▶ 启动仿真")
        self._start.setEnabled(True)
        for v in self._mv.values():
            v.setText("—")
