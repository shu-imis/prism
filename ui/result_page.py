"""结果分析"""
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QScrollArea,QSizePolicy,QFileDialog)
from PySide6.QtCore import Qt
from ui.styles import *
from ui.widgets import Card,Title,Caption,PrimaryBtn,SecondaryBtn
from report.exporter import ReportExporter
from report.generator import ProjectReport,ReportGenerator
from db.models import ReportRepository,StrategyRepository,SimulationRoundRepository

class ResultPage(QWidget):
    def __init__(self,parent=None):super().__init__(parent);self._report=None;self._build()
    def _build(self):
        l=QVBoxLayout(self);l.setContentsMargins(0,0,0,0)
        s=QScrollArea();s.setWidgetResizable(True);s.setFrameShape(QScrollArea.NoFrame);s.setStyleSheet("QScrollArea{background:transparent;border:none;padding:0;margin:0;}")
        i=QWidget();il=QVBoxLayout(i);il.setContentsMargins(0,0,PAD_XL,0);il.setSpacing(PAD_SM)
        self._sum=Card();self._sum.add(Title("推演结果",18))
        self._st=QLabel("");self._st.setStyleSheet(f"font-size:14px;font-weight:600;color:{TEXT_PRIMARY};");self._sum.add(self._st)
        self._sc=Caption("");self._sum.add(self._sc);il.addWidget(self._sum)
        self._mc=Card();self._mr=QHBoxLayout();self._mr.setSpacing(PAD_SM);self._mc.add_layout(self._mr);il.addWidget(self._mc)
        self._tc=Card();self._tc.add(Title("策略对比",14))
        self._tb=QTableWidget();self._tb.setColumnCount(6);self._tb.setHorizontalHeaderLabels(["策略","热度","情绪","支持率","评分","建议"])
        self._tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self._tc.add(self._tb);il.addWidget(self._tc)
        self._sc2=Card();self._sc2.add(Title("六维评分",14));self._sr=QVBoxLayout();self._sr.setSpacing(PAD_XS);self._sc2.add_layout(self._sr);il.addWidget(self._sc2)
        br=QHBoxLayout();br.addStretch();md=SecondaryBtn("导出 Markdown");md.clicked.connect(self._export_md);br.addWidget(md)
        pdf=PrimaryBtn("导出 PDF");pdf.clicked.connect(self._export_pdf);br.addWidget(pdf);il.addLayout(br);il.addStretch()
        s.setWidget(i);l.addWidget(s)
    def set_report(self,r):self._report=r;self._render()
    def load_results(self,pid):
        reports=ReportRepository().list_by_project(pid)
        if reports:
            import json;r=reports[0];self._report=ProjectReport(project_name=r.title,scenario_background="",executive_summary=r.summary.get("summary",""),winner=r.summary.get("winner",""))
        else:
            sl=StrategyRepository().list_by_project(pid);gen=ReportGenerator()
            for s in sl:
                rds=SimulationRoundRepository().list_by_strategy(s.id)
                if rds:
                    from core.world_state import WorldState
                    gen.add_strategy_result(s.name,s.statement,[WorldState()for _ in rds])
            self._report=gen.generate()
        self._render()
    def _render(self):
        if not self._report:return
        r=self._report;self._st.setText(f"推荐策略：{r.winner or'—'}");self._sc.setText(r.executive_summary or"")
        while self._mr.count():w=self._mr.takeAt(0);w.widget().deleteLater()if w.widget()else None
        wnr=next((s for s in r.strategy_reports if s.strategy_name==r.winner),None)
        if wnr:
            for lb,v in[("热度",f"{wnr.final_heat:.1f}"),("情绪",f"{wnr.final_sentiment:+.2f}"),("支持率",f"{wnr.final_support_rate:.0%}"),("风险",f"{len(wnr.risks)}项")]:
                c=Card(padding=PAD_SM);c.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
                vl=QLabel(v);vl.setStyleSheet(f"font-family:'JetBrains Mono';font-size:16px;font-weight:700;color:{TEXT_PRIMARY};");c.add(vl);c.add(Caption(lb));self._mr.addWidget(c)
        self._tb.setRowCount(len(r.strategy_reports))
        for i,sr in enumerate(r.strategy_reports):
            avg=sum(sr.scores.values())/max(len(sr.scores),1)
            for j,val in enumerate([sr.strategy_name,f"{sr.final_heat:.1f}",f"{sr.final_sentiment:+.2f}",f"{sr.final_support_rate:.0%}",f"{avg:.0f}",sr.recommendation]):self._tb.setItem(i,j,QTableWidgetItem(val))
        while self._sr.count():w=self._sr.takeAt(0);w.widget().deleteLater()if w.widget()else None
        if wnr:
            for dim,sc in wnr.scores.items():
                row=QHBoxLayout();row.addWidget(QLabel(dim));row.addStretch()
                bar=QLabel("█"*(int(sc)//5)+"░"*(20-int(sc)//5));bar.setStyleSheet(f"font-family:'JetBrains Mono';font-size:10px;color:{COLOR_GREEN if sc>=75 else COLOR_ORANGE};");row.addWidget(bar)
                v=QLabel(str(int(sc)));v.setStyleSheet(f"font-family:'JetBrains Mono';font-size:12px;font-weight:600;color:{TEXT_PRIMARY};");row.addWidget(v);self._sr.addLayout(row)
    def _export_md(self):
        if self._report:p,_=QFileDialog.getSaveFileName(self,"导出 Markdown","report.md","Markdown(*.md)");p and ReportExporter.export_markdown(self._report,p)
    def _export_pdf(self):
        if self._report:p,_=QFileDialog.getSaveFileName(self,"导出 PDF","report.pdf","PDF(*.pdf)");p and ReportExporter.export_pdf(self._report,p)
