"""工作区"""
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.event_page import EventPage
from ui.result_page import ResultPage
from ui.simulation_page import SimulationPage
from ui.strategy_page import StrategyPage
from ui.styles import *
from ui.widgets import Divider, PrimaryBtn, SecondaryBtn
from db.models import ReportRepository, SimulationRoundRepository, StrategyRepository
from report.exporter import ReportExporter


class ProcessPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._step = 0
        self._sim_done = False
        self._build()
        self._wire()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- 顶栏 ---
        bar = QWidget()
        bar.setFixedHeight(HEADER_H)
        bar.setStyleSheet(f"background:{TEXT_PRIMARY};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(PAD_LG, 0, PAD_LG, 0)

        self._tag = QLabel("STEP 01")
        self._tag.setStyleSheet(
            f"background:{ACCENT};color:#FFF;padding:2px 8px;"
            "font-family:'JetBrains Mono';font-size:10px;font-weight:700;"
        )
        bl.addWidget(self._tag)
        bl.addSpacing(PAD_SM)

        self._nm = QLabel("供应链搭建")
        self._nm.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{TEXT_ON_DARK};"
        )
        bl.addWidget(self._nm)
        bl.addStretch()

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#CCC;font-size:10px;")
        bl.addWidget(self._dot)
        bl.addSpacing(PAD_SM)

        self._st = QLabel("就绪")
        self._st.setStyleSheet(f"font-size:12px;color:{TEXT_ON_DARK};")
        bl.addWidget(self._st)

        layout.addWidget(bar)

        # --- 主体 ---
        body = QVBoxLayout()
        body.setContentsMargins(PAD_XL, PAD_XL, PAD_XL, 0)
        body.setSpacing(0)

        self._stack = QStackedWidget()
        self._ep = EventPage()
        self._sp = StrategyPage()
        self._smp = SimulationPage()
        self._rp = ResultPage()
        for p in [self._ep, self._sp, self._smp, self._rp]:
            self._stack.addWidget(p)
        body.addWidget(self._stack, 1)

        layout.addLayout(body, 1)

        # --- 导航 ---
        layout.addSpacing(PAD_XL)
        layout.addWidget(Divider())

        nav = QHBoxLayout()
        nav.setSpacing(PAD_MD)
        nav.setContentsMargins(PAD_XL, PAD_MD, PAD_XL, PAD_MD)

        self._back = SecondaryBtn("← 上一步")
        self._back.clicked.connect(self._prev)
        self._back.setVisible(False)
        nav.addWidget(self._back)
        nav.addStretch()

        self._next = PrimaryBtn("下一步 →")
        self._next.clicked.connect(self._next_clicked)
        nav.addWidget(self._next)
        layout.addLayout(nav)

        # --- 日志终端 ---
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(120)
        self._log.setFrameShape(QFrame.NoFrame)
        self._log.setStyleSheet(
            "QPlainTextEdit{"
            "background:#1A1A1A;color:#AAA;"
            "font-family:'JetBrains Mono','Noto Sans SC';font-size:11px;"
            "border:none;padding:6px 10px;"
            "}"
        )
        layout.addWidget(self._log)

        self._p("工作区已就绪")
        self._update()

    def _wire(self):
        self._ep.project_saved.connect(self._on_saved)
        self._sp.strategies_saved.connect(self._on_saved)
        self._smp.simulation_completed.connect(self._on_done)
        # 将终端日志接口传给各页面
        self._ep.log = self._log_msg
        self._sp.log = self._log_msg
        self._smp.log = self._log_msg

    def _log_msg(self, msg, is_error=False):
        prefix = "×" if is_error else ">"
        self._log.appendPlainText(f"  {prefix}  {msg}")

    def _on_saved(self, pid):
        self._pid = pid
        self._p(f"项目已保存（#{pid}）")
        self._advance()

    def _on_done(self, r, res):
        self._p("仿真已完成")
        self._sim_done = True
        self._update()
        self._rp.set_report(r, res)
        # 持久化（主线程）
        if self._pid:
            try:
                strategies = StrategyRepository().list_by_project(self._pid)
                round_repo = SimulationRoundRepository()
                for si, states in enumerate(res):
                    if si >= len(strategies):
                        break
                    for ws in states:
                        if ws.round == 0:
                            continue
                        round_repo.save(
                            project_id=self._pid,
                            strategy_id=strategies[si].id,
                            round_index=ws.round,
                            simulated_hour=ws.simulated_hour,
                            inventory_level=ws.inventory_level,
                            cost_index=ws.cost_index,
                            delivery_delay=ws.delivery_delay,
                            service_level=ws.service_level,
                            profit_margin=ws.profit_margin,
                            resilience_score=ws.resilience_score,
                            state=ws.to_dict(),
                            agent_messages=[],
                        )
                self._p("仿真数据已保存")

                md = ReportExporter.to_markdown(r)
                html = ReportExporter.export_html(r)
                ReportRepository().save(
                    project_id=self._pid,
                    title=f"{r.project_name} - 供应链决策推演报告",
                    markdown=md,
                    html=html,
                    summary=r.to_dict(),
                )
            except Exception as e:
                self._p(f"数据保存失败：{e}")

    def _next_clicked(self):
        if self._step == 0:
            self._ep._save()
        elif self._step == 1:
            if self._sim_done:
                self._advance()
            else:
                self._sp._save()
        elif self._step == 2:
            if self._sim_done:
                self._advance()
            else:
                self._smp._toggle()

    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._update()
            self._pass()

    def _advance(self):
        if self._step < 3:
            self._step += 1
            self._update()
            self._pass()

    def _pass(self):
        if not self._pid:
            return
        if self._step == 1:
            self._sp.load_project(self._pid)
        elif self._step == 2:
            self._smp.load_project(self._pid)
        elif self._step == 3:
            self._rp.load_results(self._pid)

    def _update(self):
        nums = ["01", "02", "03", "04"]
        names = ["供应链搭建", "行为体决策配置", "供应链仿真", "决策结果分析"]
        self._tag.setText(f"STEP {nums[self._step]}")
        self._nm.setText(names[self._step])
        self._stack.setCurrentIndex(self._step)
        self._back.setVisible(self._step > 0)

        if self._step == 2:
            if self._sim_done:
                self._next.setText("下一步 →")
            else:
                self._next.setText("▶ 启动仿真")
            self._next.setVisible(True)
        elif self._step == 3:
            self._next.setVisible(False)
        else:
            self._next.setText("下一步 →")
            self._next.setVisible(True)

    def _p(self, msg):
        self._log.appendPlainText(f"  >  {msg}")

    def load_project(self, pid):
        self._pid = pid
        self._step = 0
        self._update()
        self._log.clear()
        self._ep.load_project(pid)
        self._p(f"项目已加载（#{pid}）")
        # 检查是否有已完成的历史仿真
        reports = ReportRepository().list_by_project(pid)
        self._sim_done = bool(reports)
        if self._sim_done:
            self._smp.load_project(pid)    # 预加载 Step 3 历史
            self._rp.load_results(pid)     # 预加载 Step 4 报告

    def stop_worker(self):
        """安全停止仿真工作线程，供主窗口关闭时调用。"""
        self._smp.stop_worker()

    def reset(self):
        self._pid = None
        self._step = 0
        self._sim_done = False
        self._update()
        self._log.clear()
        self._ep.reset_for_new_project()
        self._sp.reset()
        self._smp.reset_for_new_project()
        self._p("工作区已就绪")
