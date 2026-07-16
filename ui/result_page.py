"""结果分析"""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.world_state import WorldState, KeyEvent
from db.models import ReportRepository, SimulationRoundRepository, StrategyRepository
from report.exporter import ReportExporter
from report.generator import ProjectReport, ReportGenerator, StrategyReport
from ui.styles import *
from ui.widgets import Caption, Card, PrimaryBtn, SecondaryBtn, Title


class ResultPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._report = None
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

        # --- 结果摘要 ---
        self._sum = Card()
        self._sum.add(Title("推演结果", 18))
        self._st = QLabel("")
        self._st.setStyleSheet(
            f"font-size:14px;font-weight:600;color:{TEXT_PRIMARY};"
        )
        self._sum.add(self._st)
        self._sc = Caption("")
        self._sum.add(self._sc)
        il.addWidget(self._sum)

        # --- 推荐方案指标卡 ---
        self._mc = Card()
        self._mr = QHBoxLayout()
        self._mr.setSpacing(PAD_SM)
        self._mc.add_layout(self._mr)
        il.addWidget(self._mc)

        # --- 方案对比表格 ---
        self._tc = Card()
        self._tc.add(Title("方案对比", 14))
        self._tb = QTableWidget()
        self._tb.setColumnCount(9)
        self._tb.setHorizontalHeaderLabels([
            "方案", "库存", "成本", "交付延迟",
            "服务水平", "利润率", "韧性", "评分", "建议",
        ])
        self._tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tc.add(self._tb)
        il.addWidget(self._tc)

        # --- 六维评分 ---
        self._sc2 = Card()
        self._sc2.add(Title("六维评分", 14))
        self._sr = QVBoxLayout()
        self._sr.setSpacing(PAD_XS)
        self._sc2.add_layout(self._sr)
        il.addWidget(self._sc2)

        # --- 导出按钮 ---
        br = QHBoxLayout()
        br.addStretch()
        md_btn = SecondaryBtn("导出 Markdown")
        md_btn.clicked.connect(self._export_md)
        br.addWidget(md_btn)
        pdf_btn = PrimaryBtn("导出 PDF")
        pdf_btn.clicked.connect(self._export_pdf)
        br.addWidget(pdf_btn)
        il.addLayout(br)
        il.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def set_report(self, r):
        self._report = r
        self._render()

    def load_results(self, pid):
        reports = ReportRepository().list_by_project(pid)
        if reports:
            r = reports[0]
            self._report = ProjectReport(
                project_name=r.title,
                scenario_background="",
                executive_summary=r.summary.get("summary", ""),
                winner=r.summary.get("winner", ""),
            )
            for sr_data in r.summary.get("strategy_reports", []):
                self._report.strategy_reports.append(StrategyReport(
                    strategy_name=sr_data.get("strategy_name", ""),
                    strategy_decision=sr_data.get("strategy_decision", ""),
                    final_inventory=sr_data.get("final_inventory", 0.0),
                    final_cost=sr_data.get("final_cost", 0.0),
                    final_delivery_delay=sr_data.get("final_delivery_delay", 0.0),
                    final_service_level=sr_data.get("final_service_level", 0.0),
                    final_profit_margin=sr_data.get("final_profit_margin", 0.0),
                    inventory_delta=sr_data.get("inventory_delta", 0.0),
                    cost_delta=sr_data.get("cost_delta", 0.0),
                    delay_delta=sr_data.get("delay_delta", 0.0),
                    service_delta=sr_data.get("service_delta", 0.0),
                    margin_delta=sr_data.get("margin_delta", 0.0),
                    scores=sr_data.get("scores", {}),
                    key_events=sr_data.get("key_events", []),
                    summary=sr_data.get("summary", ""),
                    recommendation=sr_data.get("recommendation", ""),
                    risks=sr_data.get("risks", []),
                ))
        else:
            sl = StrategyRepository().list_by_project(pid)
            gen = ReportGenerator()
            for s in sl:
                rds = SimulationRoundRepository().list_by_strategy(s.id)
                if rds:
                    states = []
                    for rd in rds:
                        ws = WorldState(
                            round=rd.round_index,
                            simulated_hour=rd.simulated_hour,
                            inventory_level=rd.inventory_level,
                            cost_index=rd.cost_index,
                            delivery_delay=rd.delivery_delay,
                            service_level=rd.service_level,
                            profit_margin=rd.profit_margin,
                            resilience_score=rd.resilience_score,
                        )
                        if rd.state_json:
                            state_data = json.loads(rd.state_json)
                            ws.key_events = [
                                KeyEvent(**e) for e in state_data.get("key_events", [])
                            ]
                        states.append(ws)
                    gen.add_strategy_result(s.name, s.decision, states)
            self._report = gen.generate()
        self._render()

    def _render(self):
        if not self._report:
            return

        r = self._report
        self._st.setText(f"推荐方案：{r.winner or '—'}")
        self._sc.setText(r.executive_summary or "")

        # 清空指标卡
        while self._mr.count():
            w = self._mr.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        wnr = next(
            (s for s in r.strategy_reports if s.strategy_name == r.winner),
            None,
        )
        if wnr:
            metrics = [
                ("库存", f"{wnr.final_inventory:.1f}"),
                ("成本", f"{wnr.final_cost:.1f}"),
                ("交付延迟", f"{wnr.final_delivery_delay:.1f}"),
                ("服务水平", f"{wnr.final_service_level:.0%}"),
                ("利润率", f"{wnr.final_profit_margin:+.1%}"),
                ("风险", f"{len(wnr.risks)}项"),
            ]
            for lb, v in metrics:
                c = Card(padding=PAD_SM)
                c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                vl = QLabel(v)
                vl.setStyleSheet(
                    "font-family:'JetBrains Mono';font-size:16px;"
                    f"font-weight:700;color:{TEXT_PRIMARY};"
                )
                c.add(vl)
                c.add(Caption(lb))
                self._mr.addWidget(c)

        # 填充对比表格
        self._tb.setRowCount(len(r.strategy_reports))
        for i, sr in enumerate(r.strategy_reports):
            avg = sum(sr.scores.values()) / max(len(sr.scores), 1)
            resilience = sr.scores.get("风险抵御", 0)
            row_data = [
                sr.strategy_name,
                f"{sr.final_inventory:.1f}",
                f"{sr.final_cost:.1f}",
                f"{sr.final_delivery_delay:.1f}",
                f"{sr.final_service_level:.0%}",
                f"{sr.final_profit_margin:+.1%}",
                f"{resilience:.0f}",
                f"{avg:.0f}",
                sr.recommendation,
            ]
            for j, val in enumerate(row_data):
                self._tb.setItem(i, j, QTableWidgetItem(val))

        # 六维评分条
        while self._sr.count():
            w = self._sr.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        if wnr:
            for dim, sc in wnr.scores.items():
                row = QHBoxLayout()
                row.addWidget(QLabel(dim))
                row.addStretch()

                bar_fill = int(sc) // 5
                bar_empty = 20 - bar_fill
                bar = QLabel("█" * bar_fill + "░" * bar_empty)
                color = COLOR_GREEN if sc >= 75 else COLOR_ORANGE
                bar.setStyleSheet(
                    f"font-family:'JetBrains Mono';font-size:10px;color:{color};"
                )
                row.addWidget(bar)

                v = QLabel(str(int(sc)))
                v.setStyleSheet(
                    "font-family:'JetBrains Mono';font-size:12px;"
                    f"font-weight:600;color:{TEXT_PRIMARY};"
                )
                row.addWidget(v)
                self._sr.addLayout(row)

    def _export_md(self):
        if self._report:
            p, _ = QFileDialog.getSaveFileName(
                self, "导出 Markdown", "report.md", "Markdown(*.md)",
            )
            if p:
                ReportExporter.export_markdown(self._report, p)

    def _export_pdf(self):
        if self._report:
            p, _ = QFileDialog.getSaveFileName(
                self, "导出 PDF", "report.pdf", "PDF(*.pdf)",
            )
            if p:
                ReportExporter.export_pdf(self._report, p)
