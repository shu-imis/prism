"""事件录入"""
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QScrollArea,QFileDialog,QSizePolicy)
from PySide6.QtCore import Qt,Signal
from ui.styles import *
from ui.widgets import Card,Title,Caption,Input,PrimaryBtn,SecondaryBtn
from core.document_importer import import_documents,chunk_text,MAX_IMPORT_FILES,MAX_IMPORT_TOTAL_CHARS
from db.models import ProjectRepository,KnowledgeRepository

class EventPage(QWidget):
    project_saved=Signal(int)
    def __init__(self,parent=None):super().__init__(parent);self._pid=None;self._imported=[];self._build()
    def _build(self):
        l=QVBoxLayout(self);l.setContentsMargins(0,0,0,0)
        s=QScrollArea();s.setWidgetResizable(True);s.setFrameShape(QScrollArea.NoFrame);s.setStyleSheet("QScrollArea{background:transparent;border:none;padding:0;margin:0;}")
        i=QWidget();il=QVBoxLayout(i);il.setContentsMargins(0,0,PAD_XL,0);il.setSpacing(PAD_SM)
        c=Card();c.add(Title("事件录入",14))
        c.add(QLabel("标题"));self._title=Input("例：某品牌食品安全事件");c.add(self._title)
        c.add(QLabel("行业"));self._industry=QComboBox();self._industry.setEditable(True);self._industry.addItems(["餐饮/新消费","互联网平台","汽车/出行","医药健康","金融服务","其他"]);c.add(self._industry)
        c.add(QLabel("事件背景"));self._bg=QTextEdit();self._bg.setPlaceholderText("描述事件起因、发展和当前态势...");self._bg.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);c.add(self._bg)
        c.add(Caption(f"可导入PDF/Word/Markdown/TXT，最多{MAX_IMPORT_FILES}个文件，{MAX_IMPORT_TOTAL_CHARS}字"))
        imp=SecondaryBtn("导入背景文档");imp.clicked.connect(self._import_docs);c.add(imp)
        c.add(QLabel("企业现有声明"));self._stmt=QTextEdit();self._stmt.setPlaceholderText("企业已发布的公开声明...");c.add(self._stmt)
        hr=QHBoxLayout();hr.addWidget(QLabel("初始热度"));self._heat=QSpinBox();self._heat.setRange(1,100);self._heat.setValue(45);hr.addWidget(self._heat)
        hr.addWidget(QLabel("情绪基线"));self._sent=QDoubleSpinBox();self._sent.setRange(-1,1);self._sent.setSingleStep(0.05);self._sent.setDecimals(2);self._sent.setValue(-0.2);hr.addWidget(self._sent);hr.addStretch();c.add_layout(hr)
        il.addWidget(c);il.addStretch()
        self._err=QLabel("");self._err.setStyleSheet(f"color:{COLOR_RED};font-size:12px;");self._err.setVisible(False);il.addWidget(self._err)
        self._save_btn=PrimaryBtn("保存并配置策略 →");self._save_btn.clicked.connect(self._save);il.addWidget(self._save_btn)
        s.setWidget(i);l.addWidget(s)
    def load_project(self,pid):
        p=ProjectRepository().get_by_id(pid)
        if p:self._pid=p.id;s=p.scenario;self._title.setText(s.get("title",""));self._bg.setPlainText(s.get("background",""));self._stmt.setPlainText(s.get("company_statement",""));self._heat.setValue(s.get("initial_heat",45));self._sent.setValue(s.get("baseline_sentiment",-0.2))
    def reset_for_new_project(self):self._pid=None;self._imported=[];self._title.clear();self._bg.clear();self._stmt.clear();self._heat.setValue(45);self._sent.setValue(-0.2)
    def _import_docs(self):
        files,_=QFileDialog.getOpenFileNames(self,"导入文档","","文档(*.pdf *.docx *.md *.txt)")
        if files:
            try:self._imported=import_documents(files);self._save_btn.setText(f"已导入{len(self._imported)}个文档 — 保存并继续 →")
            except Exception as e:self._err.setText(f"导入失败：{e}");self._err.setVisible(True)
    def _save(self):
        t=self._title.text().strip()
        if len(t)>80:self._err.setText("标题不能超过80字");self._err.setVisible(True);return
        bg=self._bg.toPlainText().strip()
        if not bg:self._err.setText("请填写事件背景");self._err.setVisible(True);return
        repo=ProjectRepository()
        sc={"title":t,"industry":self._industry.currentText(),"background":bg,"company_statement":self._stmt.toPlainText().strip(),"initial_heat":self._heat.value(),"baseline_sentiment":self._sent.value()}
        if self._pid:p=repo.update_scenario(self._pid,sc);pid=p.id
        else:p=repo.create(t,sc);pid=p.id;self._pid=pid
        if self._imported:KnowledgeRepository().replace_for_project(pid,[{"source":d.path,"chunk_index":i,"content":c}for d in self._imported for i,c in enumerate(chunk_text(d.text))])
        self.project_saved.emit(pid)
