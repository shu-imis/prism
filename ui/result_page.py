"""演化结果分析（Step 04）

报告式布局：深色结论横幅（结论/KPI）→ AI 综合分析（叙事主角）→
指标演化曲线 → 六维评估 + 风险 → 演化过程泳道图 → 明细数据（默认折叠）→ 导出。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.world_state import WorldState
from db.models import (
    MAIN_SIMULATION_NAME,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from llm.analysis import analyze_evolution
from llm.config import build_llm_client
from report.exporter import ReportExporter
from report.generator import ReportGenerator, SimulationReport
from ui.ai_worker import run_ai_task
from ui.charts import MetricsChart, RadarChart, SwimlaneGrid
from ui.styles import *
from ui.widgets import Caption, Card, GhostBtn, SecondaryBtn, Title

_METRIC_COLUMNS = ("周期", "库存", "成本", "交付延迟", "服务水平", "利润率")

# 横幅 KPI：标签、末值字段、delta 字段、格式、方向语义
_KPIS = [
    ("库存", "final_inventory", "inventory_delta", "{:.1f}", "{:+.1f}", "neutral"),
    ("成本", "final_cost", "cost_delta", "{:.1f}", "{:+.1f}", "down_good"),
    ("交付延迟", "final_delivery_delay", "delay_delta", "{:.1f}", "{:+.1f}", "down_good"),
    ("服务水平", "final_service_level", "service_delta", "{:.0%}", "{:+.2f}", "up_good"),
    ("利润率", "final_profit_margin", "margin_delta", "{:+.1%}", "{:+.1%}", "up_good"),
]

# 深色背景上的语义色（比页面版更亮一档）
_DARK_GOOD = "#9CC49C"
_DARK_BAD = "#D98C8C"
_DARK_MUTED = "#8A8A86"
_DARK_TEXT = "#F5F5F2"


class ResultPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._report = None
        self._rounds = []
        self._pid = None
        self._build()

    # --- 构建 UI 骨架 ---

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, PAD_XL, 0)
        inner_layout.setSpacing(PAD_SM)

        # --- 1. 深色结论横幅 ---
        banner = QWidget()
        banner.setObjectName("reportBanner")
        banner.setStyleSheet(f"#reportBanner{{background:{TEXT_PRIMARY};}}")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(PAD_LG, PAD_LG, PAD_LG, PAD_LG)
        bl.setSpacing(PAD_MD)

        title_row = QHBoxLayout()
        banner_title = QLabel("演化结果分析")
        tfont = QFont()
        tfont.setPointSize(15)
        tfont.setBold(True)
        banner_title.setFont(tfont)
        banner_title.setStyleSheet(f"color:{_DARK_TEXT};")
        title_row.addWidget(banner_title)
        self._banner_project = QLabel("")
        self._banner_project.setStyleSheet(f"font-size:12px;color:{_DARK_MUTED};")
        title_row.addWidget(self._banner_project)
        title_row.addStretch()
        bl.addLayout(title_row)

        # 结论独占一行：窄窗口下可折行，不把横幅撑出横向滚动
        self._verdict = QLabel("")
        self._verdict.setWordWrap(True)
        vfont = QFont()
        vfont.setPointSize(12)
        vfont.setBold(True)
        self._verdict.setFont(vfont)
        bl.addWidget(self._verdict)

        self._banner_summary = QLabel("")
        self._banner_summary.setWordWrap(True)
        self._banner_summary.setStyleSheet(f"font-size:12px;color:#AAAAA5;")
        bl.addWidget(self._banner_summary)

        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(PAD_XL)
        bl.addLayout(self._kpi_row)
        inner_layout.addWidget(banner)

        # --- 2. AI 综合分析（叙事主角） ---
        self._ai_card = Card()
        ai_header = QHBoxLayout()
        ai_header.addWidget(Title("AI 综合分析", 14))
        ai_header.addStretch()
        self._ai_btn = GhostBtn("生成 AI 分析")
        self._ai_btn.clicked.connect(self._generate_ai_analysis)
        ai_header.addWidget(self._ai_btn)
        self._ai_card.add_layout(ai_header)
        self._ai_body = QVBoxLayout()
        self._ai_body.setSpacing(PAD_XS)
        self._ai_card.add_layout(self._ai_body)
        inner_layout.addWidget(self._ai_card)

        # --- 3. 指标演化曲线 ---
        chart_card = Card()
        chart_header = QHBoxLayout()
        chart_header.addWidget(Title("指标演化", 14))
        chart_hint = QLabel("各指标按自身取值范围归一化")
        chart_hint.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        chart_header.addStretch()
        chart_header.addWidget(chart_hint)
        chart_card.add_layout(chart_header)
        self._chart = MetricsChart()
        self._chart.setFixedHeight(260)
        chart_card.add(self._chart)
        inner_layout.addWidget(chart_card)

        # --- 4. 双栏：六维评估雷达 + 风险与建议 ---
        eval_row = QHBoxLayout()
        eval_row.setSpacing(PAD_SM)

        radar_card = Card()
        radar_card.add(Title("演化结果评估", 14))
        self._radar = RadarChart()
        radar_card.add(self._radar)
        eval_row.addWidget(radar_card, 3)

        self._risk_card = Card()
        self._risk_card.add(Title("风险与建议", 14))
        self._risk_body = QVBoxLayout()
        self._risk_body.setSpacing(PAD_XS)
        self._risk_card.add_layout(self._risk_body)
        self._risk_card.add_stretch()
        eval_row.addWidget(self._risk_card, 2, Qt.AlignTop)
        inner_layout.addLayout(eval_row)

        # --- 5. 演化过程泳道图 ---
        swim_card = Card()
        swim_header = QHBoxLayout()
        swim_header.addWidget(Title("演化过程", 14))
        swim_hint = QLabel("点击色块查看行动详情；红色周期含关键事件")
        swim_hint.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        swim_header.addStretch()
        swim_header.addWidget(swim_hint)
        swim_card.add_layout(swim_header)
        self._swimlane = SwimlaneGrid()
        swim_card.add(self._swimlane)
        inner_layout.addWidget(swim_card)

        # --- 6. 明细数据（默认折叠） ---
        self._detail_btn = GhostBtn("展开明细数据 ▾")
        self._detail_btn.clicked.connect(self._toggle_detail)
        detail_row = QHBoxLayout()
        detail_row.addWidget(self._detail_btn)
        detail_row.addStretch()
        inner_layout.addLayout(detail_row)

        self._table_card = Card()
        self._table_card.add(Title("指标演化数据", 14))
        self._table_grid = QGridLayout()
        self._table_grid.setSpacing(0)
        self._table_card.add_layout(self._table_grid)
        self._table_card.setVisible(False)
        inner_layout.addWidget(self._table_card)

        # --- 导出 ---
        button_row = QHBoxLayout()
        button_row.addStretch()
        md_btn = SecondaryBtn("导出 Markdown")
        md_btn.clicked.connect(self._export_md)
        button_row.addWidget(md_btn)
        inner_layout.addLayout(button_row)
        inner_layout.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    # --- 公开接口 ---

    def set_report(self, report: SimulationReport, rounds=None, project_id=None):
        self._report = report
        self._rounds = list(rounds or [])
        if project_id is not None:
            self._pid = project_id
        self._render()

    def load_results(self, project_id):
        self._pid = project_id
        self._rounds = self._load_rounds(project_id)

        reports = ReportRepository().list_by_project(project_id)
        if reports:
            self._report = SimulationReport.from_dict(reports[0].summary)
        elif self._rounds:
            generator = ReportGenerator()
            generator.add_simulation_result(self._rounds)
            self._report = generator.generate()
        else:
            self._report = None

        self._render()

    # --- 数据加载 ---

    def _load_rounds(self, project_id):
        main_record = next(
            (s for s in SimulationRepository().list_by_project(project_id)
             if s.name == MAIN_SIMULATION_NAME),
            None,
        )
        if main_record is None:
            return []
        states = []
        for record in SimulationRoundRepository().list_by_simulation(main_record.id):
            try:
                state = WorldState.from_dict(record.state)
            except Exception:
                state = WorldState(
                    round=record.round_index,
                    simulated_hour=record.simulated_hour,
                    inventory_level=record.inventory_level,
                    cost_index=record.cost_index,
                    delivery_delay=record.delivery_delay,
                    service_level=record.service_level,
                    profit_margin=record.profit_margin,
                    resilience_score=record.resilience_score,
                )
            states.append(state)
        return states

    # --- 渲染 ---

    def reset(self):
        """清空页面（新建项目或切换到无数据项目时调用）。"""
        self._report = None
        self._rounds = []
        self._pid = None
        self._clear_all_sections()

    def _clear_all_sections(self):
        self._banner_project.setText("")
        self._banner_summary.setText("")
        self._verdict.setText("")
        self._clear_layout(self._kpi_row)
        self._clear_layout(self._ai_body)
        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("生成 AI 分析")
        self._chart.set_rounds([])
        self._radar.set_scores({})
        self._clear_layout(self._risk_body)
        self._swimlane.set_rounds([])
        self._clear_layout(self._table_grid)
        self._table_card.setVisible(False)
        self._detail_btn.setText("展开明细数据 ▾")

    def _render(self):
        if not self._report:
            self._clear_all_sections()
            return
        report = self._report

        self._render_banner(report)
        self._render_ai_analysis()
        self._chart.set_rounds(self._rounds)
        self._radar.set_scores(report.scores)
        self._render_risks(report)
        self._swimlane.set_rounds(self._rounds)
        self._render_metrics_table()

    # --- 深色横幅 ---

    def _render_banner(self, report: SimulationReport):
        meta = report.project_name or ""
        if report.generated_at:
            meta = f"{meta}　·　{report.generated_at[:16].replace('T', ' ')}".strip("　")
        self._banner_project.setText(meta)
        self._banner_summary.setText(report.evolution_summary or "")

        rec = report.recommendation
        if "健康" in rec or "可参照" in rec:
            color = _DARK_GOOD
        elif "可控" in rec:
            color = COLOR_ORANGE
        else:
            color = _DARK_BAD
        self._verdict.setText(rec)
        self._verdict.setStyleSheet(f"color:{color};")

        self._clear_layout(self._kpi_row)
        for label, final_field, delta_field, fmt, dfmt, direction in _KPIS:
            final_value = getattr(report, final_field)
            delta = getattr(report, delta_field)

            item = QVBoxLayout()
            item.setSpacing(2)
            value_label = QLabel(fmt.format(final_value))
            value_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:18px;"
                f"font-weight:700;color:{_DARK_TEXT};"
            )
            item.addWidget(value_label)

            sub = QHBoxLayout()
            sub.setSpacing(PAD_XS)
            name_label = QLabel(label)
            name_label.setStyleSheet(f"font-size:10px;color:{_DARK_MUTED};")
            sub.addWidget(name_label)
            delta_label = QLabel(_format_delta(delta, dfmt))
            delta_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:10px;"
                f"color:{_dark_delta_color(delta, direction)};"
            )
            sub.addWidget(delta_label)
            sub.addStretch()
            item.addLayout(sub)

            self._kpi_row.addLayout(item)
        self._kpi_row.addStretch()

    # --- AI 综合分析 ---

    def _render_ai_analysis(self):
        self._clear_layout(self._ai_body)
        analysis = (self._report.ai_analysis if self._report else {}) or {}
        self._ai_btn.setText("↺ 重新生成" if analysis else "生成 AI 分析")

        if not analysis:
            self._ai_body.addWidget(Caption(
                "由 LLM 对仿真过程做叙述式解读（趋势归因、风险传导、可执行建议），"
                "与六维评估互为补充。"
            ))
            return

        text = QLabel(analysis.get("evolution_analysis", ""))
        text.setWordWrap(True)
        text.setStyleSheet(f"font-size:13px;color:{TEXT_PRIMARY};")
        self._ai_body.addWidget(text)

        risk_text = analysis.get("risk_analysis", "")
        if risk_text:
            self._ai_body.addWidget(Caption("风险归因"))
            risk_label = QLabel(risk_text)
            risk_label.setWordWrap(True)
            risk_label.setStyleSheet(f"font-size:12px;color:{COLOR_RED};")
            self._ai_body.addWidget(risk_label)

        recommendations = analysis.get("recommendations", [])
        if recommendations:
            self._ai_body.addWidget(Caption("AI 建议"))
            for item in recommendations:
                rec_label = QLabel(f"• {item}")
                rec_label.setWordWrap(True)
                rec_label.setStyleSheet(f"font-size:12px;color:{TEXT_SECONDARY};")
                self._ai_body.addWidget(rec_label)

    def _generate_ai_analysis(self):
        if not self._report:
            return
        client = build_llm_client()
        if client is None:
            self._clear_layout(self._ai_body)
            self._ai_body.addWidget(Caption(
                "未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key"
            ))
            return
        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("AI 分析中…")
        report, rounds, pid = self._report, list(self._rounds), self._pid
        run_ai_task(
            self,
            lambda: analyze_evolution(client, report, rounds),
            lambda analysis: self._on_ai_analysis(analysis, pid),
            lambda err: self._on_ai_analysis_error(err, pid),
        )

    def _reset_ai_btn(self):
        self._ai_btn.setEnabled(True)
        analysis = (self._report.ai_analysis if self._report else {}) or {}
        self._ai_btn.setText("↺ 重新生成" if analysis else "生成 AI 分析")

    def _on_ai_analysis(self, analysis, pid):
        # 等待期间用户可能已切换项目：只有仍在原项目时才渲染并落库
        if pid != self._pid or not self._report:
            self._reset_ai_btn()  # 早退也要恢复按钮，避免永久禁用
            return
        self._report.ai_analysis = analysis
        self._render_ai_analysis()
        self._reset_ai_btn()
        # 落库：更新项目主报告（无则插入），AI 分析随报告持久化
        if self._pid:
            try:
                ReportRepository().save_or_update_latest(
                    project_id=self._pid,
                    title=f"{self._report.project_name} - 供应链演化仿真报告",
                    markdown=ReportExporter.to_markdown(self._report, self._rounds),
                    summary=self._report.to_dict(),
                )
            except Exception:
                pass  # 展示已成功，落库失败不影响查看

    def _on_ai_analysis_error(self, err, pid):
        self._reset_ai_btn()
        # 与成功路径一致：pid 不匹配说明已切换项目，不用旧错误覆盖当前界面
        if pid != self._pid:
            return
        self._clear_layout(self._ai_body)
        self._ai_body.addWidget(Caption(f"AI 分析失败：{err}"))

    # --- 风险与建议 ---

    def _render_risks(self, report: SimulationReport):
        self._clear_layout(self._risk_body)
        if report.risks:
            for risk in report.risks:
                risk_label = QLabel(f"⚠ {risk}")
                risk_label.setWordWrap(True)
                risk_label.setStyleSheet(f"font-size:12px;color:{COLOR_RED};")
                self._risk_body.addWidget(risk_label)
        else:
            no_risk = QLabel("暂无显著风险信号")
            no_risk.setStyleSheet(f"font-size:12px;color:{TEXT_MUTED};")
            self._risk_body.addWidget(no_risk)

    # --- 明细数据 ---

    def _toggle_detail(self):
        visible = not self._table_card.isVisible()
        self._table_card.setVisible(visible)
        self._detail_btn.setText("收起明细数据 ▴" if visible else "展开明细数据 ▾")

    def _render_metrics_table(self):
        """按周期渲染指标快照表格（等宽数字、右对齐）。"""
        self._clear_layout(self._table_grid)
        if not self._rounds:
            self._table_grid.addWidget(Caption("暂无轮次数据"), 0, 0)
            return
        for col, title in enumerate(_METRIC_COLUMNS):
            header = QLabel(title)
            header.setStyleSheet(
                f"font-size:11px;color:{TEXT_MUTED};padding:2px 8px;"
                f"border-bottom:1px solid {BORDER};"
            )
            header.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table_grid.addWidget(header, 0, col)
        for row, state in enumerate(self._rounds, start=1):
            values = (
                str(state.round),
                f"{state.inventory_level:.1f}",
                f"{state.cost_index:.1f}",
                f"{state.delivery_delay:.1f}",
                f"{state.service_level:.0%}",
                f"{state.profit_margin:+.1%}",
            )
            for col, value in enumerate(values):
                cell = QLabel(value)
                cell.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                cell.setStyleSheet(
                    "font-family:'JetBrains Mono';font-size:12px;"
                    f"color:{TEXT_PRIMARY};padding:2px 8px;"
                    f"border-bottom:1px solid {BORDER_LIGHT};"
                )
                self._table_grid.addWidget(cell, row, col)

    # --- 布局工具 ---

    @staticmethod
    def _clear_layout(layout):
        """递归移除 layout 中的所有子项（先隐藏，避免 deleteLater 前的残影）。"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setVisible(False)
                item.widget().deleteLater()
            elif item.layout():
                ResultPage._clear_layout(item.layout())

    # --- 导出 ---

    def _export_md(self):
        if not self._report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", "report.md", "Markdown(*.md)",
        )
        if path:
            ReportExporter.export_markdown(self._report, path, self._rounds)


def _format_delta(delta: float, fmt: str) -> str:
    if abs(delta) < 1e-9:
        return "±0"
    arrow = "↑" if delta > 0 else "↓"
    return f"{fmt.format(delta)}{arrow}"


def _dark_delta_color(delta: float, direction: str) -> str:
    if abs(delta) < 1e-9 or direction == "neutral":
        return _DARK_MUTED
    good = (delta > 0) == (direction == "up_good")
    return _DARK_GOOD if good else _DARK_BAD
