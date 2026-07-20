"""演化结果分析"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
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
from report.exporter import ReportExporter
from report.generator import ReportGenerator, SimulationReport
from report.timeline import (
    AGENT_NAMES,
    build_timeline_entries,
    format_rounds_span,
)
from ui.styles import *
from ui.text_utils import normalize_speech
from ui.widgets import Caption, Card, SecondaryBtn, Title

_METRIC_COLUMNS = ("周期", "库存", "成本", "交付延迟", "服务水平", "利润率")


class ScoreBar(QWidget):
    """QPainter 绘制的评分条 — 替代 █/░ 字符条。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_score(self, score: int):
        self._score = max(0, min(100, score))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        # Track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BORDER))
        painter.drawRect(0, 0, w, h)

        # Fill
        if self._score > 0:
            fill_w = int(w * self._score / 100)
            if self._score >= 75:
                color = QColor(COLOR_GREEN)
            elif self._score >= 50:
                color = QColor(COLOR_ORANGE)
            else:
                color = QColor(COLOR_RED)
            painter.setBrush(color)
            painter.drawRect(0, 0, fill_w, h)

        painter.end()


class ResultPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._report = None
        self._rounds = []
        self._build()

    # --- 构建 UI 骨架 ---

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
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, PAD_XL, 0)
        inner_layout.setSpacing(PAD_SM)

        # --- 演化概述 ---
        self._summary_card = Card()
        header = QHBoxLayout()
        header.addWidget(Title("演化概述", 18))
        header.addStretch()
        self._rec_badge = QLabel("")
        self._rec_badge.setVisible(False)
        header.addWidget(self._rec_badge)
        self._summary_card.add_layout(header)
        self._summary_text = Caption("")
        self._summary_card.add(self._summary_text)
        inner_layout.addWidget(self._summary_card)

        # --- 末态指标卡 ---
        self._metrics_card = Card()
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(PAD_SM)
        self._metrics_card.add_layout(self._metrics_row)
        inner_layout.addWidget(self._metrics_card)

        # --- 演化时间线（关键事件与行为体行动按周期交织） ---
        self._timeline_card = Card()
        self._timeline_card.add(Title("演化时间线", 14))
        self._timeline_layout = QVBoxLayout()
        self._timeline_layout.setSpacing(PAD_XS)
        self._timeline_card.add_layout(self._timeline_layout)
        inner_layout.addWidget(self._timeline_card)

        # --- 底部并排：指标演化数据表 + 演化结果评估 ---
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(PAD_SM)

        self._table_card = Card()
        self._table_card.add(Title("指标演化数据", 14))
        self._table_grid = QGridLayout()
        self._table_grid.setSpacing(0)
        self._table_card.add_layout(self._table_grid)
        bottom_row.addWidget(self._table_card, 3)

        self._score_card = Card()
        self._score_card.add(Title("演化结果评估", 14))
        self._score_rows = QVBoxLayout()
        self._score_rows.setSpacing(PAD_MD)
        self._score_card.add_layout(self._score_rows)
        # 评估卡按内容自然高度顶对齐，不与表格卡强制同高
        bottom_row.addWidget(self._score_card, 2, Qt.AlignTop)

        inner_layout.addLayout(bottom_row)

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

    def set_report(self, report: SimulationReport, rounds=None):
        self._report = report
        self._rounds = list(rounds or [])
        self._render()

    def load_results(self, project_id):
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

    def _render(self):
        if not self._report:
            return

        report = self._report
        self._summary_text.setText(report.evolution_summary or "")

        # --- 综合建议徽章 ---
        rec = report.recommendation
        if "健康" in rec or "可参照" in rec:
            badge_color = COLOR_GREEN
        elif "可控" in rec:
            badge_color = COLOR_ORANGE
        else:
            badge_color = COLOR_RED
        self._rec_badge.setText(rec)
        self._rec_badge.setStyleSheet(
            f"font-size:11px;font-weight:600;color:{badge_color};"
            f"border:1px solid {badge_color};padding:2px 10px;"
        )
        self._rec_badge.setVisible(bool(rec))

        # --- 末态指标卡 ---
        while self._metrics_row.count():
            item = self._metrics_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        metrics = [
            ("库存", f"{report.final_inventory:.1f}"),
            ("成本", f"{report.final_cost:.1f}"),
            ("交付延迟", f"{report.final_delivery_delay:.1f}"),
            ("服务水平", f"{report.final_service_level:.0%}"),
            ("利润率", f"{report.final_profit_margin:+.1%}"),
            ("风险", f"{len(report.risks)}项"),
        ]
        for label, value in metrics:
            card = Card(padding=PAD_SM)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            value_label = QLabel(value)
            value_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:16px;"
                f"font-weight:700;color:{TEXT_PRIMARY};"
            )
            card.add(value_label)
            card.add(Caption(label))
            self._metrics_row.addWidget(card)

        # --- 指标演化数据表 ---
        self._render_metrics_table()

        # --- 演化时间线 ---
        self._render_timeline()

        # --- 六维评估条 ---
        self._clear_layout(self._score_rows)
        for dimension, score in report.scores.items():
            row = QHBoxLayout()
            row.setSpacing(PAD_SM)

            dim_label = QLabel(dimension)
            dim_label.setFixedWidth(72)
            dim_label.setStyleSheet(
                f"font-size:12px;color:{TEXT_PRIMARY};"
            )
            row.addWidget(dim_label)

            bar = ScoreBar()
            bar.set_score(int(score))
            row.addWidget(bar)

            score_label = QLabel(str(int(score)))
            score_label.setFixedWidth(32)
            score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            score_label.setStyleSheet(
                "font-family:'JetBrains Mono';font-size:12px;"
                f"font-weight:600;color:{TEXT_PRIMARY};"
            )
            row.addWidget(score_label)

            self._score_rows.addLayout(row)

        # --- 风险列表 ---
        self._score_rows.addWidget(Caption("风险"))
        if report.risks:
            for risk in report.risks:
                risk_label = QLabel(f"⚠ {risk}")
                risk_label.setWordWrap(True)
                risk_label.setStyleSheet(f"font-size:12px;color:{COLOR_RED};")
                self._score_rows.addWidget(risk_label)
        else:
            no_risk = QLabel("暂无显著风险信号")
            no_risk.setStyleSheet(f"font-size:12px;color:{TEXT_MUTED};")
            self._score_rows.addWidget(no_risk)

    # --- 指标演化数据表 ---

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

    # --- 演化时间线 ---

    def _render_timeline(self):
        """渲染演化时间线：关键事件与聚合后的行为体行动按周期交织。"""
        self._clear_layout(self._timeline_layout)
        entries = build_timeline_entries(self._rounds)
        if not entries:
            self._timeline_layout.addWidget(Caption("本轮演化无关键事件与行为体行动"))
            return
        for entry in entries:
            row = (
                self._event_row(entry["round"], entry["description"])
                if entry["kind"] == "event"
                else self._episode_row(entry)
            )
            self._timeline_layout.addWidget(row)

    @staticmethod
    def _event_row(round_index: int, description: str) -> QLabel:
        label = QLabel(
            f"<b>周期 {round_index}</b>　"
            f"<span style='color:{COLOR_RED}'>⚡ {description}</span>"
        )
        label.setWordWrap(True)
        label.setStyleSheet(f"font-size:12px;color:{TEXT_SECONDARY};")
        return label

    @staticmethod
    def _episode_row(episode) -> QLabel:
        start, end = episode["start"], episode["end"]
        rounds_text = format_rounds_span(start, end)
        name = AGENT_NAMES.get(episode["agent_id"], f"行为体{episode['agent_id']}")
        action = ""
        if episode["action_type"]:
            action = f" <span style='color:{TEXT_MUTED}'>【{episode['action_type']}】</span>"
        reaction = ""
        if episode["reaction_to"] and episode["reaction_to"] != "none":
            reaction = f" <span style='color:{COLOR_BLUE}'>回应@{episode['reaction_to']}</span>"
        duration = ""
        if end > start:
            duration = f" <span style='color:{TEXT_MUTED}'>（持续 {end - start + 1} 轮）</span>"
        label = QLabel(
            f"<b>{rounds_text}</b>　{name}{action}{reaction}：{normalize_speech(episode['summary'])}{duration}"
        )
        label.setWordWrap(True)
        label.setStyleSheet(f"font-size:12px;color:{TEXT_SECONDARY};")
        return label

    # --- 布局工具 ---

    @staticmethod
    def _clear_layout(layout):
        """递归移除 layout 中的所有子项。"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
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
