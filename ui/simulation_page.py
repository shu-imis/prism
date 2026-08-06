"""仿真运行"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_config, DB_PATH
from core.agent_factory import AgentFactory
from core.scenario_parser import Scenario
from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from db.database import Database
from db.models import (
    MAIN_SIMULATION_NAME,
    CheckpointRepository,
    KnowledgeRepository,
    ProjectRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from llm.analysis import analyze_evolution
from llm.config import active_vendor_label, build_llm_client
from report.generator import ReportGenerator
from ui.styles import *
from core.text_utils import normalize_speech
from ui.widgets import (
    Caption,
    Card,
    GhostBtn,
    PrimaryBtn,
    ProgressBar,
    SecondaryBtn,
    Title,
)


class SimWorker(QThread):
    progress = Signal(int, int, str)
    round_done = Signal(dict)
    # 注意：不能定义名为 finished 的信号，会覆盖 QThread.finished(void)。
    # QThread.finished 由 Qt 在 run() 返回后自动发射，用于触发线程清理；
    # 被覆盖会导致 Qt6Core 内部状态机错乱，触发 __fastfail(FAST_FAIL_FATAL_APP_EXIT)。
    succeeded = Signal(int, object, list)  # 携带项目 id，防跨项目串扰
    failed = Signal(str)
    recoverable = Signal(str)      # 中断但可恢复

    def __init__(self, pid, llm, rounds):
        super().__init__()
        self.pid = pid
        self.llm = llm
        self.rounds = rounds
        self._paused = False
        self._cancelled = False
        self._checkpoint = None
        self._engine = None
        self._pending_round = None  # 暂停期间缓存的最新一轮负载，恢复后补发

    def set_checkpoint(self, checkpoint):
        self._checkpoint = checkpoint

    def pause(self):
        """暂停（协作式）：引擎在当前轮完成后于下一轮前挂起。"""
        self._paused = True
        if self._engine is not None:
            self._engine.pause()

    def resume(self):
        """恢复暂停中的仿真（不重建线程）。"""
        self._paused = False
        if self._engine is not None:
            self._engine.resume()
        # 补发暂停期间缓存的最新一轮，避免 UI 日志/指标卡跳轮
        if self._pending_round is not None:
            payload, self._pending_round = self._pending_round, None
            self.round_done.emit(payload)

    def cancel(self):
        """请求取消（协作式，由主线程调用）。

        通过引擎的 abort() 机制让仿真在当前 LLM 调用完成后
        保存检查点并干净退出，避免 terminate() 带来的数据风险。
        """
        self._cancelled = True
        self._paused = True
        self._pending_round = None  # 取消后不再补发暂停期缓存的轮次
        if self._engine is not None:
            self._engine.abort()

    def _relay_round(self, state, messages):
        """转发引擎轮次回调：暂停期间只缓存最新一轮，恢复后由 resume() 补发。"""
        payload = {
            "round": state.round,
            "inventory": state.inventory_level,
            "cost": state.cost_index,
            "delay": state.delivery_delay,
            "service": state.service_level,
            "margin": state.profit_margin,
            "resilience": state.resilience_score,
            "messages": messages,
        }
        if self._paused:
            self._pending_round = payload
        else:
            self.round_done.emit(payload)

    def run(self):
        try:
            db = Database(DB_PATH)
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

            engine = SimulationEngine(self.llm)
            self._engine = engine
            engine.configure(
                agents, sc,
                seed_events=seed_events,
                max_rounds=self.rounds,
                project_id=self.pid,
                simulation_record=sim_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                knowledge_repository=KnowledgeRepository(db) if self.pid else None,
                resume_checkpoint=self._checkpoint,
            )
            engine.set_progress_callback(
                lambda c, t, m: self.progress.emit(c, t, m)
            )
            engine.set_round_callback(self._relay_round)

            results = engine.run()
            # 发射结果前检查是否被取消：取消则直接返回，让 QThread.finished 自然触发清理
            if self._cancelled:
                return
            gen = ReportGenerator(
                proj.name if proj else "",
                sc.background,
            )
            gen.add_simulation_result(results)
            report = gen.generate()
            # Step4 全链路 AI：生成叙述式综合分析；失败则降级为纯公式报告
            try:
                report.ai_analysis = analyze_evolution(self.llm, report, results)
            except Exception:
                pass

            self.succeeded.emit(self.pid, report, results)
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
    simulation_completed = Signal(int, object, list)  # 携带项目 id，防跨项目串扰
    state_changed = Signal()  # 仿真运行状态变化（启动/暂停/结束），供工作区状态指示联动
    open_settings = Signal()  # 请求跳转到全局「设置」页

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._running = False
        self._worker = None
        self._signals_cleaned = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, PAD_XL, 0)
        il.setSpacing(PAD_SM)

        # --- 当前 AI 配置（在「设置」页统一管理） ---
        cfg = Card()
        cfg_header = QHBoxLayout()
        cfg_header.addWidget(Title("AI 配置", 13))
        cfg_header.addStretch()
        go_btn = GhostBtn("前往设置 →")
        go_btn.clicked.connect(self.open_settings.emit)
        cfg_header.addWidget(go_btn)
        cfg.add_layout(cfg_header)
        self._llm_caption = Caption("")
        cfg.add(self._llm_caption)
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
            f"QTextEdit{{background:{BG_INPUT};border:1px solid {BORDER};font-size:12px;"
            f"padding:0px;}}"
        )
        # 滚动条贴控件右边框（padding=0），文本左右间距由 viewport margins 对称控制
        self._log.setViewportMargins(8, 5, 8, 5)
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

        self._refresh_llm_caption()

    def showEvent(self, event):
        # 设置页可能刚改过配置，每次进入刷新展示
        self._refresh_llm_caption()
        super().showEvent(event)

    def _refresh_llm_caption(self):
        if build_llm_client(max_retries=1) is None:
            self._llm_caption.setText(
                "尚未配置 LLM API Key，请到左侧「设置」页完成配置后再启动仿真"
            )
        else:
            self._llm_caption.setText(f"当前 AI 配置：{active_vendor_label()}（在「设置」页修改）")

    def log(self, text: str, is_error: bool = False):
        """向日志区追加一行，错误信息以红色显示。"""
        if is_error:
            self._log.append(f"<span style='color:#CC3333'>{text}</span>")
        else:
            self._log.append(text)

    def load_project(self, pid):
        # 切换项目：取消旧仿真并断开其信号（不阻塞等待，引擎存检查点后自行退出）
        self._orphan_worker()
        self._pid = pid
        self._reset()
        self._load_history()

    def reset_for_new_project(self):
        self._orphan_worker()
        self._pid = None
        self._reset()

    @staticmethod
    def _disconnect_worker_signals(worker):
        """断开 worker 的业务信号；已断开或 C++ 对象已销毁时静默跳过。"""
        try:
            worker.progress.disconnect()
            worker.round_done.disconnect()
            worker.succeeded.disconnect()
            worker.failed.disconnect()
            worker.recoverable.disconnect()
        except (RuntimeError, TypeError):
            pass

    def _orphan_worker(self):
        """取消式接管旧 worker：请求取消并解除信号绑定后立刻放手。

        与 _dispose_worker 不同，这里不 wait() 阻塞 UI 线程；引擎在当前
        LLM 调用完成后保存检查点自行退出，旧项目以后可断点恢复。
        """
        worker = self._worker
        if worker is None:
            return
        try:
            worker.resume()  # 解除暂停，确保 abort 能在下一轮前生效
            worker.cancel()
        except RuntimeError:
            pass  # C++ 对象已被 deleteLater 清理
        self._disconnect_worker_signals(worker)
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.connect(worker.deleteLater)
        except RuntimeError:
            pass
        self._worker = None
        self._signals_cleaned = False

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

        # 完成判定与 ProcessPage._is_sim_done 同源，以 DB 项目状态为准；
        # 致命失败后可能残留轮次但状态非 completed，此时必须允许重新启动
        project = ProjectRepository().get_by_id(self._pid)
        if project and project.status == "completed":
            self._bar.setValue(100)
            self._st.setText("仿真已完成")
            self._st.setVisible(True)
            self._start.setText("✓ 已完成")
            self._start.setEnabled(False)
        else:
            self._st.setText("上次仿真未完成，可重新启动")
            self._st.setVisible(True)
            self._start.setText("▶ 启动仿真")
            self._start.setEnabled(True)
        self._running = False

    def _toggle(self):
        if self._running:
            if self._worker:
                self._worker.pause()
            self._running = False
            self._start.setText("▶ 继续")
            self.state_changed.emit()
            return

        # 暂停中的 worker 直接恢复，不重建线程、不作废进行中的轮次
        if self._worker is not None and self._worker._paused and self._worker.isRunning():
            self._worker.resume()
            self._running = True
            self._start.setText("⏸ 暂停")
            self.state_changed.emit()
            return

        # 替换旧 worker 前必须等其线程真正结束，否则对运行中的 QThread
        # 调用 disconnect/deleteLater 会触发 use-after-free 崩溃。
        self._dispose_worker()

        llm = build_llm_client(max_retries=1)
        if llm is None:
            self.log("未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key", is_error=True)
            return

        self._worker = SimWorker(
            self._pid,
            llm,
            app_config.sim.max_rounds,
        )
        if self._pid:
            cp_repo = CheckpointRepository()
            checkpoint = cp_repo.latest_for_project(self._pid)
            if checkpoint:
                self._worker.set_checkpoint(checkpoint)
                self.log("检测到检查点，从断点恢复", is_error=False)
            else:
                # 全新启动：清掉上次运行残留的轮次，避免轮次 upsert 跨次混杂
                main = next(
                    (s for s in SimulationRepository().list_by_project(self._pid)
                     if s.name == MAIN_SIMULATION_NAME),
                    None,
                )
                if main:
                    SimulationRoundRepository().delete_for_simulation(main.id)
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
        """同步等待旧 worker 线程结束后安全清理。调用方在主线程。

        取消后等待线程自行退出（引擎在当前 LLM 调用完成后保存检查点
        并干净结束），超时取 LLM 请求上限留足余量。
        """
        w = self._worker
        if w is None:
            return
        try:
            w.cancel()
            w.wait(35000)
        except RuntimeError:
            pass  # C++ 对象已被 deleteLater 清理
        if not self._signals_cleaned:
            self._disconnect_worker_signals(w)
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
        self._disconnect_worker_signals(w)
        self._signals_cleaned = True
        # 注意：不在此处置 self._worker = None，否则 _toggle 重启时无法
        # 调用 _dispose_worker 等待旧线程。deleteLater 足以保证对象回收。

    def _on_succeeded(self, pid, report, results):
        self._running = False
        self._bar.setValue(100)
        self._start.setText("✓ 完成")
        self._start.setEnabled(False)
        self.simulation_completed.emit(pid, report, results)
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

        仅发送取消信号，不阻塞等待。引擎在 LLM 调用完成后自行保存
        检查点并退出，线程结束不影响进程关闭。
        """
        if self._worker is None:
            return
        try:
            self._worker.cancel()
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
        self._st.setVisible(False)
        self._log.clear()
        self._start.setText("▶ 启动仿真")
        self._start.setEnabled(True)
        for v in self._mv.values():
            v.setText("—")
