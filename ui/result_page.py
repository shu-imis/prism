"""结果分析页。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QTextBrowser, QVBoxLayout, QWidget

from report.exporter import ReportExporter
from ui.widgets import BodyLabel, PrismCard, SectionTitle


class ResultPage(QWidget):
    """展示仿真结果和报告。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

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

        layout.addWidget(SectionTitle("结果分析"))
        self.summary_label = BodyLabel("完成一次真实 LLM 推演后，报告会显示在这里。")
        layout.addWidget(self.summary_label)

        self.metric_row = QHBoxLayout()
        layout.addLayout(self.metric_row)

        analysis_card = PrismCard()
        analysis_card.addWidget(SectionTitle("关键结论"))
        self.analysis_label = BodyLabel("暂无关键事件。")
        analysis_card.addWidget(self.analysis_label)
        layout.addWidget(analysis_card)

        report_card = PrismCard()
        report_card.addWidget(SectionTitle("推演评估报告"))
        self.report_view = QTextBrowser()
        self.report_view.setOpenExternalLinks(True)
        self.report_view.setMinimumHeight(460)
        report_card.addWidget(self.report_view)
        layout.addWidget(report_card)
        layout.addStretch()

    def set_demo_result(self, report, results) -> None:
        """接收 SimulationPage 产生的报告并刷新展示。"""

        winner = report.winner or "暂无"
        self.summary_label.setText(f"综合评分推荐策略：{winner}。{report.executive_summary}")
        self._clear_metric_row()
        for strategy_report in report.strategy_reports:
            self.metric_row.addWidget(
                self._metric_card(
                    strategy_report.strategy_name,
                    f"热度 {strategy_report.final_heat:.1f}\n"
                    f"情绪 {strategy_report.final_sentiment:.2f}\n"
                    f"支持率 {strategy_report.final_support_rate:.1%}",
                )
            )
        self.metric_row.addStretch()
        self.analysis_label.setText(self._build_analysis_text(report, results))
        self.report_view.setHtml(ReportExporter.export_html(report))

    def _metric_card(self, title: str, value: str) -> PrismCard:
        card = PrismCard(padding=14)
        card.setMinimumWidth(220)
        card.addWidget(QLabel(title))
        card.addWidget(BodyLabel(value))
        return card

    def _clear_metric_row(self) -> None:
        while self.metric_row.count():
            item = self.metric_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _build_analysis_text(report, results) -> str:
        lines = []
        if report.winner:
            lines.append(f"推荐策略：{report.winner}")
        for strategy_report in report.strategy_reports:
            risks = "；".join(strategy_report.risks) if strategy_report.risks else "暂无明显高风险信号"
            events = "；".join(strategy_report.key_events[:6]) if strategy_report.key_events else "无关键事件"
            lines.append(
                f"{strategy_report.strategy_name}：{strategy_report.recommendation}。"
                f"风险：{risks}。关键事件：{events}。"
            )
        if results:
            total_rounds = sum(max(len(rounds) - 1, 0) for rounds in results)
            lines.append(f"本次共完成 {len(results)} 个策略、{total_rounds} 个模拟轮次。")
        return "\n".join(lines) if lines else "暂无结果。"
