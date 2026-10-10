"""工作区"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.event_page import EventPage
from ui.persona_page import PersonaPage
from ui.result_page import ResultPage
from ui.scroll import ChainingPlainTextEdit
from ui.simulation_page import SimulationPage
from ui.styles import (
    BORDER,
    COLOR_GREEN,
    HEADER_H,
    PAD_LG,
    PAD_MD,
    PAD_SM,
    PAD_XL,
    STATUS_COLORS,
    STATUS_LABELS,
    TEXT_MUTED,
    TEXT_ON_DARK,
    small_text_qss,
    terminal_qss,
    workspace_bar_qss,
    workspace_step_name_qss,
    workspace_step_tag_qss,
)
from ui.widgets import Divider, PrimaryBtn, SecondaryBtn, StatusDot
from db.models import (
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
        bar.setStyleSheet(workspace_bar_qss())
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(PAD_LG, 0, PAD_LG, 0)

        self._tag = QLabel("STEP 01")
        self._tag.setStyleSheet(workspace_step_tag_qss())
        bl.addWidget(self._tag)
        bl.addSpacing(PAD_SM)

        self._nm = QLabel("供应链搭建")
        self._nm.setStyleSheet(workspace_step_name_qss())
        bl.addWidget(self._nm)
        bl.addStretch()

        self._dot = StatusDot(BORDER)
        bl.addWidget(self._dot)
        bl.addSpacing(PAD_SM)

        self._st = QLabel("就绪")
        self._st.setStyleSheet(small_text_qss(TEXT_ON_DARK))
        bl.addWidget(self._st)

        layout.addWidget(bar)

        # --- 主体 ---
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
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
        self._log = ChainingPlainTextEdit()
        self._log.setObjectName("terminalLog")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(120)
        self._log.setFrameShape(QFrame.NoFrame)
        self._log.setStyleSheet(terminal_qss())
        # 文本左起对齐内容列 PAD_XL：视口边距 20 + 文档隐式边距 4；滚动条贴控件右边框
        self._log.setViewportMargins(PAD_XL - 4, 6, PAD_XL - 4, 6)
        layout.addWidget(self._log)

        self._log_msg("工作区已就绪")
        self._update()

    def _wire(self):
        self._ep.project_saved.connect(self._on_saved)
        self._sp.agents_saved.connect(self._on_saved)
        self._smp.simulation_completed.connect(self._on_done)
        self._smp.state_changed.connect(self._update)
        self._smp.open_settings.connect(self.open_settings.emit)
        # 将终端日志出口注入各页面
        self._ep.log = self._log_msg
        self._sp.log = self._log_msg
        self._smp.set_log_sink(self._log_msg)

    def _log_msg(self, msg, is_error=False):
        prefix = "×" if is_error else ">"
        self._log.appendPlainText(f"{prefix}  {msg}")

    def _on_saved(self, pid):
        self._pid = pid
        self._saved_steps.add(self._step)
        self._log_msg(f"项目已保存（#{pid}）")
        self._advance()

    def _on_done(self, pid, r, res):
        if pid is None or pid != self._pid:
            # 旧 worker 完成时当前可能已切换到其他项目，忽略避免跨项目串扰
            return
        self._log_msg("仿真已完成")
        self._update()
        self._rp.set_report(r, res, project_id=self._pid)
        # 持久化报告（主线程）；仿真轮次已由引擎自行落库
        try:
            repo = ProjectRepository()
            project = repo.get_by_id(self._pid)
            if project:
                repo.update_scenario(
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
            self._log_msg(f"数据保存失败：{e}")

    def _next_clicked(self):
        if self._step == 0:
            self._ep.save()
        elif self._step == 1:
            if self._is_sim_done():
                self._advance()
            else:
                self._sp.save()
        elif self._step == 2:
            if self._is_sim_done():
                self._advance()
            else:
                self._smp.toggle()

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
            self._rp.load_project(self._pid)

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
                self._next.setEnabled(True)
            else:
                # 主动作状态（启动/暂停/继续/恢复/重试）由仿真页统一维护
                self._next.setText(self._smp._action_label)
                self._next.setEnabled(self._smp._action_enabled)
            self._next.setVisible(True)
        elif self._step == 3:
            self._next.setVisible(False)
        else:
            self._next.setText("下一步 →")
            self._next.setEnabled(True)
            self._next.setVisible(True)

        # 右上角步骤状态指示（圆点与文案同色）
        status_text, status_color = self._step_status()
        self._st.setText(status_text)
        self._st.setStyleSheet(small_text_qss(status_color))
        self._dot.set_color(status_color)

    def _step_status(self) -> tuple[str, str]:
        """当前步骤的状态文案与颜色。"""
        if self._step in (0, 1):
            if self._step in self._saved_steps:
                return "已保存", COLOR_GREEN
            return "编辑中", TEXT_MUTED
        if self._step == 2:
            if self._smp.is_running():
                return STATUS_LABELS["running"], STATUS_COLORS["running"]
            if self._pid:
                project = ProjectRepository().get_by_id(self._pid)
                if project and project.status == "interrupted":
                    return STATUS_LABELS["interrupted"], STATUS_COLORS["interrupted"]
                if project and project.status == "completed":
                    return STATUS_LABELS["completed"], STATUS_COLORS["completed"]
            return STATUS_LABELS["draft"], TEXT_MUTED
        if self._is_sim_done():
            return STATUS_LABELS["completed"], STATUS_COLORS["completed"]
        return "待仿真", TEXT_MUTED

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
            # 重启后不存在仍在运行的仿真，running 必为陈旧状态；
            # 中断的仿真同样每轮落库，须以检查点区分「中断」与「跑完」
            stale = self._heal_stale_status(
                has_checkpoint=bool(CheckpointRepository().latest_for_project(pid)),
                has_data=has_data,
            )
            ProjectRepository().update_scenario(pid, dict(project.scenario), status=stale)
        elif project and project.status == "interrupted":
            # 检查点已丢失则回退为草稿
            if not CheckpointRepository().latest_for_project(pid):
                ProjectRepository().update_scenario(pid, dict(project.scenario), status="draft")
        self._update()
        self._log.clear()
        self._ep.load_project(pid)
        self._log_msg(f"项目已加载（#{pid}）")
        if self._is_sim_done():
            self._smp.load_project(pid)    # 预加载 Step 3 历史
            self._rp.load_project(pid)     # 预加载 Step 4 报告

    @staticmethod
    def _heal_stale_status(has_checkpoint: bool, has_data: bool) -> str:
        """陈旧 running 状态的治愈判据。

        有检查点说明仿真被中断（可断点恢复）；无检查点但有轮次/报告数据
        说明已跑完；两者皆无则回到草稿。
        """
        if has_checkpoint:
            return "interrupted"
        return "completed" if has_data else "draft"

    @staticmethod
    def _has_rounds(pid) -> bool:
        """主仿真是否存在轮次数据。"""
        main_record = SimulationRepository().get_main(pid)
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

    def iter_ai_workers(self) -> list:
        """各子页面运行中的 AI worker 合并列表（供主窗口关窗前统一兜底）。"""
        workers = []
        for page in (self._ep, self._sp, self._smp, self._rp):
            workers.extend(getattr(page, "_ai_workers", None) or [])
        return workers

    def reset(self):
        self._pid = None
        self._step = 0
        self._saved_steps = set()
        self._update()
        self._log.clear()
        self._ep.reset()
        self._sp.reset()
        self._smp.reset()
        self._rp.reset()
        self._log_msg("工作区已就绪")
