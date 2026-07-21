"""工作区"""
from PySide6.QtCore import Signal
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
from ui.persona_page import PersonaPage
from ui.result_page import ResultPage
from ui.simulation_page import SimulationPage
from ui.styles import *
from ui.widgets import Divider, PrimaryBtn, SecondaryBtn
from db.models import (
    MAIN_SIMULATION_NAME,
    CheckpointRepository,
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from report.exporter import ReportExporter


class ProcessPage(QWidget):
    open_settings = Signal()  # 转发仿真页的「前往设置」请求

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._step = 0
        self._saved_steps: set[int] = set()
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
            f"background:{ACCENT};color:{TEXT_ON_DARK};padding:2px 8px;"
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
        self._dot.setStyleSheet(f"color:{BORDER};font-size:10px;")
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
        self._sp = PersonaPage()
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
        self._log.setObjectName("terminalLog")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(120)
        self._log.setFrameShape(QFrame.NoFrame)
        self._log.setStyleSheet(
            "QPlainTextEdit{"
            f"background:{BG_TERMINAL};color:#AAA;"
            "font-family:'JetBrains Mono','Noto Sans SC';font-size:11px;"
            "border:none;padding:6px 10px;"
            "}"
        )
        layout.addWidget(self._log)

        self._p("工作区已就绪")
        self._update()

    def _wire(self):
        self._ep.project_saved.connect(self._on_saved)
        self._sp.agents_saved.connect(self._on_saved)
        self._smp.simulation_completed.connect(self._on_done)
        self._smp.state_changed.connect(self._update)
        self._smp.open_settings.connect(self.open_settings.emit)
        # 将终端日志接口传给各页面
        self._ep.log = self._log_msg
        self._sp.log = self._log_msg
        self._smp.log = self._log_msg

    def _log_msg(self, msg, is_error=False):
        prefix = "×" if is_error else ">"
        self._log.appendPlainText(f"  {prefix}  {msg}")

    def _on_saved(self, pid):
        self._pid = pid
        self._saved_steps.add(self._step)
        self._p(f"项目已保存（#{pid}）")
        self._advance()

    def _on_done(self, r, res):
        self._p("仿真已完成")
        self._update()
        self._rp.set_report(r, res, project_id=self._pid)
        # 持久化报告（主线程）；仿真轮次已由引擎自行落库
        if self._pid:
            try:
                project = ProjectRepository().get_by_id(self._pid)
                if project:
                    ProjectRepository().update_scenario(
                        self._pid, dict(project.scenario), status="completed"
                    )
                md = ReportExporter.to_markdown(r, res)
                ReportRepository().save_or_update_latest(
                    project_id=self._pid,
                    title=f"{r.project_name} - 供应链演化仿真报告",
                    markdown=md,
                    summary=r.to_dict(),
                )
            except Exception as e:
                self._p(f"数据保存失败：{e}")

    def _next_clicked(self):
        if self._step == 0:
            self._ep._save()
        elif self._step == 1:
            if self._is_sim_done():
                self._advance()
            else:
                self._sp._save()
        elif self._step == 2:
            if self._is_sim_done():
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
        names = ["供应链搭建", "行为体性格配置", "供应链仿真", "演化结果分析"]
        self._tag.setText(f"STEP {nums[self._step]}")
        self._nm.setText(names[self._step])
        self._stack.setCurrentIndex(self._step)
        self._back.setVisible(self._step > 0)

        if self._step == 2:
            if self._is_sim_done():
                self._next.setText("下一步 →")
            else:
                self._next.setText("▶ 启动仿真")
            self._next.setVisible(True)
        elif self._step == 3:
            self._next.setVisible(False)
        else:
            self._next.setText("下一步 →")
            self._next.setVisible(True)

        # 右上角步骤状态指示（圆点与文案同色）
        status_text, status_color = self._step_status()
        self._st.setText(status_text)
        self._st.setStyleSheet(f"font-size:12px;color:{status_color};")
        self._dot.setStyleSheet(f"color:{status_color};font-size:10px;")

    def _step_status(self) -> tuple[str, str]:
        """当前步骤的状态文案与颜色。"""
        if self._step in (0, 1):
            if self._step in self._saved_steps:
                return "已保存", COLOR_GREEN
            return "编辑中", TEXT_MUTED
        if self._step == 2:
            if self._smp.is_running():
                return "运行中", COLOR_BLUE
            if self._pid:
                project = ProjectRepository().get_by_id(self._pid)
                if project and project.status == "interrupted":
                    return "已中断", COLOR_RED
                if project and project.status == "completed":
                    return "已完成", COLOR_GREEN
            return "草稿", TEXT_MUTED
        if self._is_sim_done():
            return "已完成", COLOR_GREEN
        return "待仿真", TEXT_MUTED

    def _p(self, msg):
        self._log.appendPlainText(f"  >  {msg}")

    def load_project(self, pid):
        self._pid = pid
        self._step = 0
        # 先确定各步骤完成态，再刷新状态指示
        reports = ReportRepository().list_by_project(pid)
        project = ProjectRepository().get_by_id(pid)
        # Step 4 的数据可从轮次重建，故有数据 = 曾有仿真运行过
        has_data = bool(reports) or self._has_rounds(pid)
        self._saved_steps = {0}
        if project and project.scenario.get("agents_config"):
            self._saved_steps.add(1)
        if project and project.status == "running":
            # 重启后不存在仍在运行的仿真，running 必为陈旧状态
            stale = "completed" if has_data else "draft"
            ProjectRepository().update_scenario(pid, dict(project.scenario), status=stale)
        elif project and project.status == "interrupted":
            # 检查点已丢失则回退为草稿
            if not CheckpointRepository().latest_for_project(pid):
                ProjectRepository().update_scenario(pid, dict(project.scenario), status="draft")
        self._update()
        self._log.clear()
        self._ep.load_project(pid)
        self._p(f"项目已加载（#{pid}）")
        if self._is_sim_done():
            self._smp.load_project(pid)    # 预加载 Step 3 历史
            self._rp.load_results(pid)     # 预加载 Step 4 报告

    @staticmethod
    def _has_rounds(pid) -> bool:
        """主仿真是否存在轮次数据。"""
        main_record = next(
            (s for s in SimulationRepository().list_by_project(pid)
             if s.name == MAIN_SIMULATION_NAME),
            None,
        )
        return bool(
            main_record
            and SimulationRoundRepository().list_by_simulation(main_record.id)
        )

    def _is_sim_done(self) -> bool:
        """仿真是否已完成（以 DB 项目状态为唯一真相来源）。"""
        if not self._pid:
            return False
        project = ProjectRepository().get_by_id(self._pid)
        return project is not None and project.status == "completed"

    def stop_worker(self):
        """安全停止仿真工作线程，供主窗口关闭时调用。"""
        self._smp.stop_worker()

    def reset(self):
        self._pid = None
        self._step = 0
        self._saved_steps = set()
        self._update()
        self._log.clear()
        self._ep.reset_for_new_project()
        self._sp.reset()
        self._smp.reset_for_new_project()
        self._rp.reset()
        self._p("工作区已就绪")
