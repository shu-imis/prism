"""策略配置"""
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTextEdit,QSpinBox,QScrollArea,QSizePolicy)
from PySide6.QtCore import Qt,Signal
from ui.styles import *
from ui.widgets import Card,Title,Caption,Input,PrimaryBtn,GhostBtn,DangerBtn
from db.models import StrategyRepository,ProjectRepository
DEFAULT=[{"name":"快速道歉与透明整改","statement":"我们向消费者诚恳致歉，已暂停涉事门店营业并启动第三方卫生检查。今晚20点前公布初步核查结果。","release_hour":4},{"name":"先核查再回应","statement":"我们已启动内部核查，将在事实确认后向公众说明情况。调查完成前请以官方信息为准。","release_hour":8}]

class StrategyPage(QWidget):
    strategies_saved=Signal(int)
    def __init__(self,parent=None):super().__init__(parent);self._pid=None;self._cards=[];self._build()
    def _build(self):
        l=QVBoxLayout(self);l.setContentsMargins(0,0,0,0)
        s=QScrollArea();s.setWidgetResizable(True);s.setFrameShape(QScrollArea.NoFrame);s.setStyleSheet("QScrollArea{background:transparent;border:none;padding:0;margin:0;}")
        i=QWidget();self._il=QVBoxLayout(i);self._il.setContentsMargins(0,0,PAD_XL,0);self._il.setSpacing(PAD_SM)
        for d in DEFAULT:self._add_card(d)
        self._il.addStretch()
        br=QHBoxLayout();add_btn=GhostBtn("＋ 添加策略");add_btn.clicked.connect(lambda:self._add_card());br.addWidget(add_btn);br.addStretch()
        self._save_btn=PrimaryBtn("保存并开始仿真 →");self._save_btn.clicked.connect(self._save);br.addWidget(self._save_btn)
        self._il.addLayout(br);s.setWidget(i);l.addWidget(s)
    def _add_card(self,data=None):
        d=data or{"name":"","statement":"","release_hour":0}
        c=Card(padding=PAD_MD);hdr=QHBoxLayout();hdr.addWidget(Title(f"策略 {len(self._cards)+1}",13));hdr.addStretch()
        if len(self._cards)>=2:rm=DangerBtn("删除");rm.clicked.connect(lambda: self._rm(c));hdr.addWidget(rm)
        c.add_layout(hdr);c.add(QLabel("策略名称"));nm=Input(d.get("name",""));c.add(nm)
        c.add(QLabel("声明稿全文"));st=QTextEdit();st.setPlainText(d.get("statement",""));st.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);c.add(st)
        tr=QHBoxLayout();tr.addWidget(QLabel("发布时间(h)"));sp=QSpinBox();sp.setRange(0,72);sp.setValue(d.get("release_hour",0));tr.addWidget(sp);tr.addStretch();c.add_layout(tr)
        self._cards.append({"card":c,"name":nm,"statement":st,"release":sp});self._il.insertWidget(self._il.count()-2,c);self._update_nums()
    def _rm(self,c):
        if len(self._cards)<=2:return
        for i,cd in enumerate(self._cards):
            if cd["card"]is c:self._il.removeWidget(c);c.deleteLater();del self._cards[i];break
        self._update_nums()
    def _update_nums(self):
        for i,cd in enumerate(self._cards):cd["card"].findChild(QLabel).setText(f"策略 {i+1}")
    def load_project(self,pid):
        self._pid=pid
        while self._cards:cd=self._cards.pop();self._il.removeWidget(cd["card"]);cd["card"].deleteLater()
        sl=StrategyRepository().list_by_project(pid)if pid else[]
        for s in(sl if sl else DEFAULT):
            d={"name":s.name if hasattr(s,'name')else s.get("name",""),"statement":s.statement if hasattr(s,'statement')else s.get("statement",""),"release_hour":s.release_hour if hasattr(s,'release_hour')else s.get("release_hour",0)}
            self._add_card(d)
    def reset(self):self._pid=None;self.load_project(None)
    def _save(self):
        if not self._pid:return
        data=[]
        for cd in self._cards:data.append({"name":cd["name"].text().strip(),"statement":cd["statement"].toPlainText().strip(),"release_hour":cd["release"].value(),"meta":{}})
        StrategyRepository().replace_for_project(self._pid,data);self.strategies_saved.emit(self._pid)
