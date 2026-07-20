"""仿真运行"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_config, DB_PATH, ROOT_DIR
from core.agent_factory import AgentFactory
from core.scenario_parser import Scenario
from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from db.database import Database
from db.models import (
    MAIN_SIMULATION_NAME,
    CheckpointRepository,
    ProjectRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.generator import ReportGenerator
from ui.styles import *
from ui.text_utils import normalize_speech
from ui.widgets import (
    Caption,
    Card,
    GhostBtn,
    Input,
    PrimaryBtn,
    ProgressBar,
    SecondaryBtn,
    SegmentedControl,
    Title,
)

PRESETS = [
    {"label": "OpenAI", "proto": "openai", "url": "https://api.openai.com/v1", "model": "gpt-5.6-sol"},
    {"label": "Anthropic", "proto": "anthropic", "url": "https://api.anthropic.com", "model": "claude-fable-5"},
    {"label": "DeepSeek", "proto": "openai", "url": "https://api.deepseek.com/v1", "model": "deepseek-v4-pro"},
    {"label": "通义千问", "proto": "openai", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen3.7-max"},
    {"label": "Kimi", "proto": "openai", "url": "https://api.moonshot.cn/v1", "model": "kimi-k2.7-code"},
    {"label": "智谱", "proto": "openai", "url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-5.2"},
    {"label": "阶跃星辰", "proto": "openai", "url": "https://api.stepfun.com/step_plan/v1", "model": "step-3.7-flash"},
    {"label": "自定义", "proto": "openai", "url": "", "model": ""},
]

# 厂商索引 → .env 环境变量前缀
VENDOR_ENV_PREFIX = {
    0: "OPENAI",
    1: "ANTHROPIC",
    2: "DEEPSEEK",
    3: "QWEN",
    4: "KIMI",
    5: "ZHIPU",
    6: "STEPFUN",
    7: "CUSTOM",
}


class SimWorker(QThread):
    progress = Signal(int, int, str)
    round_done = Signal(dict)
    # 注意：不能定义名为 finished 的信号，会覆盖 QThread.finished(void)。
    # QThread.finished 由 Qt 在 run() 返回后自动发射，用于触发线程清理；
    # 被覆盖会导致 Qt6Core 内部状态机错乱，触发 __fastfail(FAST_FAIL_FATAL_APP_EXIT)。
    succeeded = Signal(object, list)
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
        self._cancelled = False
        self._checkpoint = None

    def set_checkpoint(self, checkpoint):
        self._checkpoint = checkpoint

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def cancel(self):
        """请求取消（协作式，由主线程调用）。

        不打断进行中的仿真：engine.run() 返回后检查到取消标志，
        跳过报告生成与结果发射，直接结束线程。
        """
        self._cancelled = True
        self._paused = True

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
            scenario_dict = proj.scenario if proj else {}
            sc = Scenario.from_dict(scenario_dict)
            sim_record = (
                SimulationRepository(db).get_or_create_main(self.pid)
                if self.pid
                else None
            )
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)

            agents = AgentFactory.create_all()
            AgentFactory.apply_overrides(agents, scenario_dict.get("agents_config"))
            seed_events = scenario_dict.get("seed_events", [])

            engine = SimulationEngine(llm)
            engine.configure(
                agents, sc,
                seed_events=seed_events,
                max_rounds=self.rounds,
                project_id=self.pid,
                simulation_record=sim_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=self._checkpoint,
            )
            engine.set_progress_callback(
                lambda c, t, m: self.progress.emit(c, t, m)
            )
            engine.set_round_callback(
                lambda state, messages: (
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
            # 发射结果前检查是否被取消：取消则直接返回，让 QThread.finished 自然触发清理
            if self._cancelled:
                return
            gen = ReportGenerator(
                proj.name if proj else "",
                sc.background,
            )
            gen.add_simulation_result(results)

            self.succeeded.emit(gen.generate(), results)
        except SimulationRecoverableError as e:
            self.recoverable.emit(str(e))
        except Exception as e:
            # 致命错误：清除检查点，防止反复恢复
            if self.pid:
                try:
                    db = Database(DB_PATH)
                    CheckpointRepository(db).delete_for_project(self.pid)
                except Exception:
                    pass
            self.failed.emit(str(e))
        # run() 返回后 QThread 自动发射 finished(void) 信号，由主线程的
        # _on_worker_finished 槽断开信号连接；对象在下一次 _dispose_worker 时回收。


class SimulationPage(QWidget):
    simulation_completed = Signal(object, list)
    state_changed = Signal()  # 仿真运行状态变化（启动/暂停/结束），供工作区状态指示联动

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._running = False
        self._worker = None
        self._vendor_state: dict[int, dict[str, str]] = {}
        self._signals_cleaned = False
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
        self._provider_seg = SegmentedControl(
            [(str(i), p["label"]) for i, p in enumerate(PRESETS)]
        )
        self._provider_seg.set_value("0")
        self._provider_seg.valueChanged.connect(
            lambda v: self._on_provider_changed(int(v))
        )
        cfg.add(self._provider_seg)

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

        self._toggle_btn = GhostBtn("展开 ▼")
        self._toggle_btn.clicked.connect(self._toggle_config)
        cfg.add(self._toggle_btn)
        # 默认收起 API Key/URL/模型字段，首屏留给指标与日志
        self._config_widget.setVisible(False)
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
        rst.clicked.connect(self._on_reset)
        br.addWidget(rst)
        br.addStretch()
        il.addLayout(br)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

        # 从 .env 预填各厂商配置
        self._load_vendor_state_from_env()

    def _load_vendor_state_from_env(self):
        """从 .env 加载各厂商已保存的配置，并预填当前选中厂商。"""
        for idx, prefix in VENDOR_ENV_PREFIX.items():
            key = os.getenv(f"{prefix}_API_KEY", "")
            url = os.getenv(f"{prefix}_BASE_URL", "")
            model = os.getenv(f"{prefix}_MODEL", "")
            preset = PRESETS[idx]
            if key or url or model:
                self._vendor_state[idx] = {
                    "key": key,
                    "url": url or preset.get("url", ""),
                    "model": model or preset.get("model", ""),
                }
        # 预填默认厂商（OpenAI，index 0）
        self._apply_vendor_state(0)

    def _apply_vendor_state(self, index: int):
        """将指定厂商的状态填入 UI 控件。"""
        if index in self._vendor_state:
            state = self._vendor_state[index]
            self._key.setText(state.get("key", ""))
            self._url.setText(state.get("url", ""))
            self._model.setText(state.get("model", ""))
        else:
            p = PRESETS[index]
            self._key.setText("")
            self._url.setText(p.get("url", ""))
            self._model.setText(p.get("model", ""))

    def _save_current_vendor_state(self):
        """将当前 UI 输入保存到当前厂商的状态中。"""
        self._vendor_state[self._provider_index] = {
            "key": self._key.text(),
            "url": self._url.text(),
            "model": self._model.text(),
        }

    def _persist_to_env(self):
        """将所有厂商状态写入 .env 文件持久化。"""
        self._save_current_vendor_state()
        env_path = ROOT_DIR / ".env"
        try:
            from dotenv import set_key as dotenv_set_key
        except ImportError:
            return
        env_path_str = str(env_path)
        for idx, state in self._vendor_state.items():
            if idx not in VENDOR_ENV_PREFIX:
                continue
            prefix = VENDOR_ENV_PREFIX[idx]
            for field, suffix in [("key", "API_KEY"), ("url", "BASE_URL"), ("model", "MODEL")]:
                try:
                    dotenv_set_key(env_path_str, f"{prefix}_{suffix}", state.get(field, ""))
                except Exception:
                    pass

    def _on_provider_changed(self, index: int):
        if index == self._provider_index:
            return
        self._save_current_vendor_state()
        self._provider_index = index
        self._apply_vendor_state(index)

    def log(self, text: str, is_error: bool = False):
        """向日志区追加一行，错误信息以红色显示。"""
        if is_error:
            self._log.append(f"<span style='color:#CC3333'>{text}</span>")
        else:
            self._log.append(text)

    def _toggle_config(self):
        cv = self._config_widget
        visible = not cv.isVisible()
        cv.setVisible(visible)
        self._toggle_btn.setText("收起 ▲" if visible else "展开 ▼")

    def load_project(self, pid):
        self._pid = pid
        self._reset()
        self._load_history()

    def reset_for_new_project(self):
        self._pid = None
        self._reset()

    def _load_history(self):
        """从 DB 加载主仿真的历史轮次数据并回显到日志和指标卡。"""
        if not self._pid:
            return
        main_record = next(
            (s for s in SimulationRepository().list_by_project(self._pid)
             if s.name == MAIN_SIMULATION_NAME),
            None,
        )
        if main_record is None:
            return
        rounds = SimulationRoundRepository().list_by_simulation(main_record.id)
        if not rounds:
            return
        for r in rounds:
            self._log.append(
                f"  >  [周期 {r.round_index}]  库存 {r.inventory_level:.0f}  "
                f"成本 {r.cost_index:.0f}  服务 {r.service_level:.0%}  "
                f"利润 {r.profit_margin:+.1%}"
            )
        last_round = rounds[-1]
        self._mv["库存"].setText(f"{last_round.inventory_level:.1f}")
        self._mv["成本"].setText(f"{last_round.cost_index:.1f}")
        self._mv["服务水平"].setText(f"{last_round.service_level:.0%}")
        self._mv["利润率"].setText(f"{last_round.profit_margin:+.1%}")
        self._mv["交付延迟"].setText(f"{last_round.delivery_delay:.1f}")

        # 有检查点 = 中断态：回显历史但保留恢复入口，不标记完成
        if CheckpointRepository().latest_for_project(self._pid):
            self._bar.setValue(
                int(last_round.round_index / max(app_config.sim.max_rounds, 1) * 100)
            )
            self._st.setText("仿真中断，可从断点恢复")
            self._st.setVisible(True)
            self._start.setText("↺ 恢复仿真")
            self._start.setEnabled(True)
            self._running = False
            return

        self._bar.setValue(100)
        self._st.setText("仿真已完成")
        self._st.setVisible(True)
        self._start.setText("✓ 已完成")
        self._start.setEnabled(False)
        self._running = False

    def _toggle(self):
        if self._running:
            if self._worker:
                self._worker.pause()
            self._running = False
            self._start.setText("▶ 继续")
            self.state_changed.emit()
            return

        # 替换旧 worker 前必须等其线程真正结束，否则对运行中的 QThread
        # 调用 disconnect/deleteLater 会触发 use-after-free 崩溃。
        self._dispose_worker()

        # 持久化当前厂商及所有厂商配置到 .env
        self._persist_to_env()

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
            cp_repo = CheckpointRepository()
            checkpoint = cp_repo.latest_for_project(self._pid)
            if checkpoint:
                self._worker.set_checkpoint(checkpoint)
                self.log("检测到检查点，从断点恢复", is_error=False)
        self._worker.progress.connect(self._on_progress)
        self._worker.round_done.connect(self._on_round)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.recoverable.connect(self._on_recoverable)
        # 关键：连接 QThread 内置的 finished(void) 信号（run() 返回后由 Qt
        # 自动发射）做安全清理。不要连到 succeeded/failed/recoverable 上，
        # 因为那些信号发射时线程可能还在执行后续代码。
        self._worker.finished.connect(self._on_worker_finished)

        self._running = True
        self._start.setText("⏸ 暂停")
        if self._pid:
            # 项目状态机：启动仿真 → running，完成 → completed（见 process_page）
            project = ProjectRepository().get_by_id(self._pid)
            if project and project.status != "running":
                ProjectRepository().update_scenario(
                    self._pid, dict(project.scenario), status="running"
                )
        self._worker.start()
        self.state_changed.emit()

    def _dispose_worker(self):
        """同步等待旧 worker 线程结束后安全清理。调用方在主线程。"""
        w = self._worker
        if w is None:
            return
        try:
            w.cancel()
            if w.isRunning():
                w.quit()
                # 协作式等待：给足时间让网络请求完成，避免 terminate 导致 Qt 崩溃
                if not w.wait(5000):
                    # 最后一招：线程卡死时强制终止。仅在替换/重置场景使用，
                    # 仍有风险但优于对运行中的 QThread 做 deleteLater。
                    w.terminate()
                    w.wait(2000)
        except RuntimeError:
            pass  # C++ 对象已被 deleteLater 清理
        if not self._signals_cleaned:
            try:
                w.progress.disconnect()
                w.round_done.disconnect()
                w.succeeded.disconnect()
                w.failed.disconnect()
                w.recoverable.disconnect()
            except (RuntimeError, TypeError):
                pass
        try:
            w.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._signals_cleaned = False
        try:
            w.deleteLater()
        except RuntimeError:
            pass
        self._worker = None

    def _on_worker_finished(self):
        """QThread.run() 返回后在主线程安全断开信号连接。

        此时线程已真正结束，disconnect 不会引发 use-after-free。
        对象本身留待下一次 _dispose_worker 时通过 deleteLater 回收。
        """
        w = self._worker
        if w is None:
            return
        try:
            w.progress.disconnect()
            w.round_done.disconnect()
            w.succeeded.disconnect()
            w.failed.disconnect()
            w.recoverable.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._signals_cleaned = True
        # 注意：不在此处置 self._worker = None，否则 _toggle 重启时无法
        # 调用 _dispose_worker 等待旧线程。deleteLater 足以保证对象回收。

    def _on_succeeded(self, report, results):
        self._running = False
        self._bar.setValue(100)
        self._start.setText("✓ 完成")
        self._start.setEnabled(False)
        self.simulation_completed.emit(report, results)
        self.state_changed.emit()

    def _on_failed(self, msg):
        self._running = False
        self.log(msg, is_error=True)
        self._start.setText("▶ 重试")
        self._start.setEnabled(True)
        if self._pid:
            project = ProjectRepository().get_by_id(self._pid)
            if project and project.status == "running":
                ProjectRepository().update_scenario(
                    self._pid, dict(project.scenario), status="draft"
                )
        self.state_changed.emit()

    def _on_recoverable(self, msg):
        self._running = False
        self.log(msg, is_error=True)
        self._start.setText("↺ 恢复")
        self._start.setEnabled(True)
        if self._pid:
            project = ProjectRepository().get_by_id(self._pid)
            if project:
                ProjectRepository().update_scenario(
                    self._pid, dict(project.scenario), status="interrupted"
                )
        self.state_changed.emit()

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
                self._log.append(f"    ×  {agent_name}：{error[:80]}")
            else:
                content = normalize_speech(msg.get("content", ""))
                if content:
                    action_type = msg.get("action_type", "maintain")
                    reaction_to = msg.get("reaction_to", "none")
                    reaction = f" 回应@{reaction_to}" if reaction_to != "none" else ""
                    self._log.append(f"    ↳  {agent_name}【{action_type}】{reaction}：{content}")

    def is_running(self) -> bool:
        """仿真是否正在运行（供工作区状态指示查询）。"""
        return self._running

    def stop_worker(self):
        """安全停止工作线程，供主窗口关闭时调用。

        采用协作式取消：先设取消标志，再 quit + wait。仅当线程卡死
        超时才用 terminate 作为最后手段（仍有风险但窗口正在关闭别无选择）。
        """
        if self._worker is None:
            return
        w = self._worker
        try:
            w.cancel()
            if w.isRunning():
                w.quit()
                # 给足时间让 LLM 网络请求完成，避免 terminate 导致 Qt 崩溃
                if not w.wait(8000):
                    w.terminate()
                    w.wait(2000)
        except RuntimeError:
            pass  # C++ 对象已被 deleteLater 清理

    def _on_reset(self):
        """显式重置：停止工作线程，清除检查点与历史轮次后还原仿真页面状态。"""
        self._dispose_worker()
        if self._pid:
            CheckpointRepository().delete_for_project(self._pid)
            main = next(
                (s for s in SimulationRepository().list_by_project(self._pid)
                 if s.name == MAIN_SIMULATION_NAME),
                None,
            )
            if main:
                SimulationRoundRepository().delete_for_simulation(main.id)
            # 将项目状态回退到草稿，避免项目列表显示过期状态
            project = ProjectRepository().get_by_id(self._pid)
            if project and project.status != "draft":
                ProjectRepository().update_scenario(
                    self._pid, dict(project.scenario), status="draft"
                )
        self._reset()
        self.state_changed.emit()

    def _reset(self):
        self._running = False
        self._bar.setValue(0)
        self._st.setText("")
        self._log.clear()
        self._start.setText("▶ 启动仿真")
        self._start.setEnabled(True)
        for v in self._mv.values():
            v.setText("—")
