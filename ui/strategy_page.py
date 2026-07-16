"""行为体决策配置"""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.models import StrategyRepository
from ui.styles import *
from ui.widgets import (
    Caption,
    Card,
    DangerBtn,
    GhostBtn,
    Input,
    PrimaryBtn,
    Title,
)

DEFAULT = [
    {
        "name": "激进补货方案",
        "actor": "零售商",
        "decision": "增加安全库存至150%,提前2周期向制造商下单,同时启动促销活动刺激需求",
        "release_cycle": "1-6",
        "parameters": {
            "safety_stock_ratio": 1.5,
            "lead_time_reduction": 2,
            "promo_discount": 0.15,
        },
    },
    {
        "name": "保守观望方案",
        "actor": "制造商",
        "decision": "维持当前排产计划不变,密切监控上下游库存变化,仅在库存低于30%时触发补货",
        "release_cycle": "1-12",
        "parameters": {
            "safety_stock_threshold": 0.3,
            "reorder_trigger": "inventory_low",
        },
    },
]


class StrategyPage(QWidget):
    strategies_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = None
        self._cards = []
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
        self._il = QVBoxLayout(inner)
        self._il.setContentsMargins(0, 0, 0, 0)
        self._il.setSpacing(PAD_SM)

        card = Card()
        card.add(Title("行为体决策配置", 14))
        card.add(Caption("请配置2~4种决策方案，用于对比不同方案对供应链的影响"))
        self._il.addWidget(card)

        for d in DEFAULT:
            self._add_card(d)

        self._il.addStretch()

        br = QHBoxLayout()
        self._add_btn = GhostBtn("＋ 添加方案")
        self._add_btn.clicked.connect(self._add_card)
        br.addWidget(self._add_btn)
        br.addStretch()

        self._save_btn = PrimaryBtn("保存并开始仿真 →")
        self._save_btn.clicked.connect(self._save)
        br.addWidget(self._save_btn)
        self._il.addLayout(br)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _add_card(self, data=None):
        if len(self._cards) >= 4:
            return
        d = data or {"name": "", "actor": "", "decision": "", "release_cycle": "", "parameters": {}}

        card = Card(padding=PAD_MD)

        hdr = QHBoxLayout()
        hdr.addWidget(Title(f"方案 {len(self._cards) + 1}", 13))
        hdr.addStretch()
        if len(self._cards) >= 2:
            rm = DangerBtn("删除")
            rm.clicked.connect(lambda: self._rm(card))
            hdr.addWidget(rm)
        card.add_layout(hdr)

        card.add(QLabel("方案名称"))
        nm = Input("如：激进补货方案")
        nm.setText(str(d.get("name", "")))
        card.add(nm)

        card.add(QLabel("涉及行为体"))
        actor_row = QHBoxLayout()
        ACTOR_TYPES = [
            "原材料供应商", "制造商", "分销商", "零售商",
            "物流服务商", "消费者", "监管机构",
        ]
        selected_actor = {"val": d.get("actor", "")}
        actor_widgets = []
        for label in ACTOR_TYPES:
            lbl = QLabel(label)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.setFixedHeight(BTN_H)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.mousePressEvent = (
                lambda e, v=label, s=selected_actor, ws=actor_widgets:
                _select_actor(v, s, ws)
            )
            actor_widgets.append((label, lbl))
            actor_row.addWidget(lbl)

        def _select_actor(v, s, ws):
            s["val"] = v
            for tv, w in ws:
                if tv == v:
                    w.setStyleSheet(
                        f"background:{TEXT_PRIMARY};color:{TEXT_ON_DARK};"
                        "padding:2px 10px;font-size:12px;"
                    )
                else:
                    w.setStyleSheet(
                        f"background:transparent;color:{TEXT_MUTED};"
                        "padding:2px 10px;font-size:12px;"
                    )
        _select_actor(selected_actor["val"], selected_actor, actor_widgets)
        actor_row.addStretch()
        card.add_layout(actor_row)

        card.add(QLabel("决策内容"))
        st = QTextEdit()
        st.setPlainText(d.get("decision", ""))
        st.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.add(st)

        tr = QHBoxLayout()
        tr.addWidget(QLabel("生效周期"))
        rp = QLineEdit()
        rp.setText(d.get("release_cycle", ""))
        rp.setPlaceholderText("如 1-4")
        tr.addWidget(rp)
        tr.addStretch()
        card.add_layout(tr)

        card.add(QLabel("决策参数（JSON）"))
        pr = QTextEdit()
        pr.setPlainText(
            json.dumps(d.get("parameters", {}), ensure_ascii=False, indent=2)
        )
        pr.setMaximumHeight(80)
        card.add(pr)

        self._cards.append({
            "card": card,
            "name": nm,
            "actor": selected_actor,
            "decision": st,
            "release_cycle": rp,
            "parameters": pr,
        })
        self._il.insertWidget(self._il.count() - 2, card)
        self._update_nums()

    def _rm(self, card):
        if len(self._cards) <= 2:
            return
        for i, cd in enumerate(self._cards):
            if cd["card"] is card:
                self._il.removeWidget(card)
                card.deleteLater()
                del self._cards[i]
                break
        self._update_nums()

    def _update_nums(self):
        for i, cd in enumerate(self._cards):
            cd["card"].findChild(QLabel).setText(f"方案 {i + 1}")

    def load_project(self, pid):
        self._pid = pid
        while self._cards:
            cd = self._cards.pop()
            self._il.removeWidget(cd["card"])
            cd["card"].deleteLater()

        sl = StrategyRepository().list_by_project(pid) if pid else []
        for s in (sl if sl else DEFAULT):
            d = {
                "name": s.name if hasattr(s, "name") else s.get("name", ""),
                "actor": s.actor if hasattr(s, "actor") else s.get("actor", ""),
                "decision": s.decision if hasattr(s, "decision") else s.get("decision", ""),
                "release_cycle": s.release_cycle if hasattr(s, "release_cycle") else s.get("release_cycle", ""),
                "parameters": (
                    json.loads(s.parameters_json)
                    if hasattr(s, "parameters_json") and s.parameters_json
                    else s.get("parameters", {})
                ),
            }
            self._add_card(d)

    def reset(self):
        self._pid = None
        self.load_project(None)

    def _save(self):
        if not self._pid:
            return

        if len(self._cards) < 2:
            self.log("至少需要 2 种决策方案", is_error=True)
            return

        if len(self._cards) > 4:
            self.log("最多只能配置 4 种决策方案", is_error=True)
            return

        data = []
        for cd in self._cards:
            name = cd["name"].text().strip()
            if not name:
                self.log("请填写所有方案名称", is_error=True)
                return

            decision = cd["decision"].toPlainText().strip()
            if not decision:
                self.log("请填写所有方案的决策内容", is_error=True)
                return

            try:
                params = json.loads(cd["parameters"].toPlainText().strip())
            except json.JSONDecodeError:
                params = {}
            data.append({
                "name": name,
                "actor": cd["actor"]["val"],
                "decision": decision,
                "release_cycle": cd["release_cycle"].text().strip(),
                "parameters": params,
            })

        StrategyRepository().replace_for_project(self._pid, data)
        self.strategies_saved.emit(self._pid)
