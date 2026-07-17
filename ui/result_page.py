"""结果分析"""
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.world_state import KeyEvent, WorldState
from db.models import ReportRepository, SimulationRoundRepository, StrategyRepository
from report.exporter import ReportExporter
from report.generator import ProjectReport, ReportGenerator, StrategyReport
from ui.styles import *
from ui.widgets import Caption, Card, Divider, SecondaryBtn, Title

NODE_TYPE_LABELS = {
    "supplier": "原材料供应商",
    "manufacturer": "制造商",
    "distributor": "分销商",
    "retailer": "零售商",
    "logistics": "物流服务商",
    "consumer": "消费者",
    "regulator": "监管机构",
}


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
        self._strategy_results = {}
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

        # --- 结果摘要 ---
        self._summary_card = Card()
        self._summary_card.add(Title("推演结果", 18))
        self._winner_label = QLabel("")
        self._winner_label.setStyleSheet(
            f"font-size:14px;font-weight:600;color:{TEXT_PRIMARY};"
        )
        self._summary_card.add(self._winner_label)
        self._summary_text = Caption("")
        self._summary_card.add(self._summary_text)
        inner_layout.addWidget(self._summary_card)

        # --- 推荐方案指标卡 ---
        self._metrics_card = Card()
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(PAD_SM)
        self._metrics_card.add_layout(self._metrics_row)
        inner_layout.addWidget(self._metrics_card)

        # --- 方案对比（卡片布局）---
        self._comparison_card = Card()
        self._comparison_card.add(Title("方案对比", 14))
        self._comparison_layout = QVBoxLayout()
        self._comparison_layout.setSpacing(PAD_SM)
        self._comparison_card.add_layout(self._comparison_layout)
        inner_layout.addWidget(self._comparison_card)

        # --- 六维评分 ---
        self._score_card = Card()
        self._score_card.add(Title("六维评分", 14))
        self._score_rows = QVBoxLayout()
        self._score_rows.setSpacing(PAD_XS)
        self._score_card.add_layout(self._score_rows)
        inner_layout.addWidget(self._score_card)

        # --- 节点状态（卡片网格）---
        self._node_card = Card()
        self._node_card.add(Title("节点状态", 14))
        self._node_caption = Caption("")
        self._node_card.add(self._node_caption)
        self._node_grid = QGridLayout()
        self._node_grid.setSpacing(PAD_SM)
        self._node_card.add_layout(self._node_grid)
        inner_layout.addWidget(self._node_card)

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

    def set_report(self, report, strategy_results=None):
        self._report = report
        self._strategy_results = self._coerce_strategy_results(strategy_results)
        self._render()

    def load_results(self, project_id):
        db_results = self._load_strategy_results(project_id)
        if db_results:
            self._strategy_results = db_results

        reports = ReportRepository().list_by_project(project_id)
        if reports:
            self._report = self._project_report_from_record(reports[0])
        elif db_results:
            generator = ReportGenerator()
            for strategy in StrategyRepository().list_by_project(project_id):
                states = self._strategy_results.get(strategy.name, [])
                if states:
                    generator.add_strategy_result(strategy.name, strategy.decision, states)
            self._report = generator.generate()

        self._render()

    # --- 数据加载 ---

    def _project_report_from_record(self, record):
        summary = record.summary
        project_name = summary.get("project_name", "")
        if not project_name:
            suffix = " - 供应链决策推演报告"
            project_name = (
                record.title[:-len(suffix)]
                if record.title.endswith(suffix)
                else record.title
            )
        project_report = ProjectReport(
            project_name=project_name,
            scenario_background=summary.get("scenario_background", ""),
            executive_summary=summary.get("executive_summary", summary.get("summary", "")),
            winner=summary.get("winner", ""),
        )
        generated_at = summary.get("generated_at")
        if generated_at:
            project_report.generated_at = str(generated_at)
        project_report.recommendations = list(summary.get("recommendations", []))

        for strategy_data in summary.get("strategy_reports", []):
            project_report.strategy_reports.append(
                StrategyReport(
                    strategy_name=strategy_data.get("strategy_name", ""),
                    strategy_decision=strategy_data.get("strategy_decision", ""),
                    final_inventory=strategy_data.get("final_inventory", 0.0),
                    final_cost=strategy_data.get("final_cost", 0.0),
                    final_delivery_delay=strategy_data.get("final_delivery_delay", 0.0),
                    final_service_level=strategy_data.get("final_service_level", 0.0),
                    final_profit_margin=strategy_data.get("final_profit_margin", 0.0),
                    inventory_delta=strategy_data.get("inventory_delta", 0.0),
                    cost_delta=strategy_data.get("cost_delta", 0.0),
                    delay_delta=strategy_data.get("delay_delta", 0.0),
                    service_delta=strategy_data.get("service_delta", 0.0),
                    margin_delta=strategy_data.get("margin_delta", 0.0),
                    scores=strategy_data.get("scores", {}),
                    key_events=strategy_data.get("key_events", []),
                    summary=strategy_data.get("summary", ""),
                    recommendation=strategy_data.get("recommendation", ""),
                    risks=strategy_data.get("risks", []),
                )
            )
        return project_report

    def _coerce_strategy_results(self, strategy_results):
        if not strategy_results or not self._report:
            return {}
        mapped = {}
        for index, states in enumerate(strategy_results):
            if index >= len(self._report.strategy_reports):
                break
            mapped[self._report.strategy_reports[index].strategy_name] = list(states or [])
        return mapped

    def _load_strategy_results(self, project_id):
        loaded = {}
        round_repo = SimulationRoundRepository()
        for strategy in StrategyRepository().list_by_project(project_id):
            loaded[strategy.name] = [
                self._world_state_from_round(round_record)
                for round_record in round_repo.list_by_strategy(strategy.id)
            ]
        return loaded

    def _world_state_from_round(self, round_record):
        fallback = WorldState(
            round=round_record.round_index,
            simulated_hour=round_record.simulated_hour,
            inventory_level=round_record.inventory_level,
            cost_index=round_record.cost_index,
            delivery_delay=round_record.delivery_delay,
            service_level=round_record.service_level,
            profit_margin=round_record.profit_margin,
            resilience_score=round_record.resilience_score,
        )
        if not round_record.state_json:
            return fallback

        try:
            state_data = json.loads(round_record.state_json)
        except json.JSONDecodeError:
            return fallback

        try:
            state = WorldState.from_dict(state_data)
        except Exception:
            state = fallback
            state.key_events = []
            for event in state_data.get("key_events", []):
                state.key_events.append(
                    KeyEvent(
                        round=event.get("round", round_record.round_index),
                        simulated_hour=event.get("cycle", event.get("simulated_hour", round_record.simulated_hour)),
                        event_type=event.get("event_type", ""),
                        description=event.get("description", ""),
                        inventory_delta=event.get("inventory_delta", 0.0),
                        cost_delta=event.get("cost_delta", 0.0),
                        delay_delta=event.get("delay_delta", 0.0),
                        service_delta=event.get("service_delta", 0.0),
                        margin_delta=event.get("margin_delta", 0.0),
                    )
                )

        state.round = round_record.round_index
        state.simulated_hour = round_record.simulated_hour
        state.inventory_level = round_record.inventory_level
        state.cost_index = round_record.cost_index
        state.delivery_delay = round_record.delivery_delay
        state.service_level = round_record.service_level
        state.profit_margin = round_record.profit_margin
        state.resilience_score = round_record.resilience_score
        return state

    # --- 辅助查询 ---

    def _winning_strategy_report(self):
        if not self._report or not self._report.strategy_reports:
            return None
        if self._report.winner:
            for strategy in self._report.strategy_reports:
                if strategy.strategy_name == self._report.winner:
                    return strategy
        return self._report.strategy_reports[0]

    def _latest_state_for_strategy(self, strategy_name):
        states = self._strategy_results.get(strategy_name, [])
        return states[-1] if states else None

    # --- 渲染 ---

    def _render(self):
        if not self._report:
            return

        winner_report = self._winning_strategy_report()
        winner_name = winner_report.strategy_name if winner_report else ""

        self._winner_label.setText(f"推荐方案：{winner_name or '—'}")
        self._summary_text.setText(self._report.executive_summary or "")

        # --- 指标卡（不变）---
        while self._metrics_row.count():
            item = self._metrics_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if winner_report:
            metrics = [
                ("库存", f"{winner_report.final_inventory:.1f}"),
                ("成本", f"{winner_report.final_cost:.1f}"),
                ("交付延迟", f"{winner_report.final_delivery_delay:.1f}"),
                ("服务水平", f"{winner_report.final_service_level:.0%}"),
                ("利润率", f"{winner_report.final_profit_margin:+.1%}"),
                ("风险", f"{len(winner_report.risks)}项"),
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

        # --- 方案对比卡片 ---
        self._clear_layout(self._comparison_layout)
        for strategy in self._report.strategy_reports:
            is_winner = (strategy.strategy_name == winner_name)
            card = self._build_strategy_card(strategy, is_winner)
            self._comparison_layout.addWidget(card)

        # --- 六维评分条 ---
        self._clear_layout(self._score_rows)
        if winner_report:
            for dimension, score in winner_report.scores.items():
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

        # --- 节点状态卡片 ---
        self._clear_layout(self._node_grid)
        latest_state = self._latest_state_for_strategy(winner_name)
        if latest_state and latest_state.node_states:
            self._node_caption.setText(
                f"展示方案“{winner_name}”最近一个供应链周期的节点级状态。"
            )
            cols = 2
            for i, node in enumerate(latest_state.node_states):
                card = self._build_node_card(node)
                row_idx, col_idx = divmod(i, cols)
                self._node_grid.addWidget(card, row_idx, col_idx)
        else:
            self._node_caption.setText("当前结果中还没有节点级状态可展示")

    # --- 卡片构建 ---

    def _make_metric_tile(self, label: str, value: str, color: str | None = None):
        """创建指标展示小组件：标签在上，数值在下，居中排列。"""
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(2)

        val_color = color or TEXT_PRIMARY
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"font-family:'JetBrains Mono';font-size:14px;font-weight:700;color:{val_color};"
        )
        val_lbl.setAlignment(Qt.AlignCenter)
        ly.addWidget(val_lbl)

        cap = Caption(label)
        cap.setAlignment(Qt.AlignCenter)
        ly.addWidget(cap)

        return w

    def _build_strategy_card(self, strategy: StrategyReport, is_winner: bool) -> QWidget:
        """构建单个方案的对比卡片。"""
        card = Card(padding=PAD_MD)

        # --- 头部：方案名 + 推荐标签 ---
        header = QHBoxLayout()
        header.setSpacing(PAD_SM)
        name_lbl = QLabel(strategy.strategy_name)
        name_lbl.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{TEXT_PRIMARY};"
        )
        header.addWidget(name_lbl)
        header.addStretch()

        # 推荐标签
        rec = strategy.recommendation
        if "优先" in rec:
            badge_color = COLOR_GREEN
        elif "修改" in rec:
            badge_color = COLOR_ORANGE
        else:
            badge_color = COLOR_RED
        badge = QLabel(rec)
        badge.setStyleSheet(
            f"font-size:10px;font-weight:600;color:{badge_color};"
            f"border:1px solid {badge_color};padding:1px 8px;"
        )
        header.addWidget(badge)
        card.add_layout(header)

        card.add(Divider())

        # --- 指标网格 ---
        resilience = strategy.scores.get("风险抵御", 0)
        average_score = (
            sum(strategy.scores.values()) / max(len(strategy.scores), 1)
        )

        grid = QGridLayout()
        grid.setSpacing(PAD_SM)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)

        metrics = [
            ("库存", f"{strategy.final_inventory:.1f}"),
            ("成本", f"{strategy.final_cost:.1f}"),
            ("交付延迟", f"{strategy.final_delivery_delay:.1f}"),
            ("服务水平", f"{strategy.final_service_level:.0%}"),
            ("利润率", f"{strategy.final_profit_margin:+.1%}"),
            ("韧性", f"{resilience:.0f}"),
            ("评分", f"{average_score:.0f}"),
        ]
        for idx, (label, value) in enumerate(metrics):
            row_idx, col_idx = divmod(idx, 4)
            grid.addWidget(self._make_metric_tile(label, value), row_idx, col_idx)

        # 建议放在最后一行剩余位置
        if len(metrics) % 4 != 0:
            rec_label = QLabel(strategy.recommendation)
            rec_label.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
            rec_label.setAlignment(Qt.AlignCenter)
            grid.addWidget(rec_label, len(metrics) // 4, len(metrics) % 4, 1, 4 - len(metrics) % 4)

        card.add_layout(grid)

        # --- 风险提示 ---
        if strategy.risks:
            risks_text = " · ".join(strategy.risks[:2])
            risk_lbl = Caption(risks_text)
            risk_lbl.setStyleSheet(f"font-size:10px;color:{COLOR_RED};")
            risk_lbl.setWordWrap(True)
            card.add(risk_lbl)

        # --- 优胜方案金色左边框 ---
        if is_winner:
            wrapper = QWidget()
            wrapper_ly = QHBoxLayout(wrapper)
            wrapper_ly.setContentsMargins(0, 0, 0, 0)
            wrapper_ly.setSpacing(0)
            accent_bar = QFrame()
            accent_bar.setFixedWidth(3)
            accent_bar.setStyleSheet(f"background:{ACCENT};border:none;")
            wrapper_ly.addWidget(accent_bar)
            wrapper_ly.addWidget(card)
            return wrapper

        return card

    def _build_node_card(self, node) -> QWidget:
        """构建单个供应链节点的状态卡片。"""
        card = Card(padding=PAD_MD)

        # --- 头部：节点名 + 类型标签 ---
        header = QHBoxLayout()
        header.setSpacing(PAD_SM)
        name_lbl = QLabel(node.name)
        name_lbl.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{TEXT_PRIMARY};"
        )
        header.addWidget(name_lbl)
        header.addStretch()

        type_label = NODE_TYPE_LABELS.get(node.node_type, node.node_type or "-")
        type_badge = QLabel(type_label)
        type_badge.setStyleSheet(
            f"font-size:10px;color:{TEXT_MUTED};border:1px solid {BORDER};"
            f"padding:1px 8px;"
        )
        header.addWidget(type_badge)
        card.add_layout(header)

        card.add(Divider())

        # --- 指标网格 2 行 ---
        grid = QGridLayout()
        grid.setSpacing(PAD_SM)
        for c in range(4):
            grid.setColumnStretch(c, 1)

        row0 = [
            ("库存", f"{node.inventory:.1f}"),
            ("产能", f"{node.capacity:.1f}"),
            ("交付周期", f"{node.lead_time:.1f}"),
            ("成本", f"{node.cost_index:.1f}"),
        ]
        for col, (label, value) in enumerate(row0):
            grid.addWidget(self._make_metric_tile(label, value), 0, col)

        row1 = [
            ("服务水平", f"{node.service_level:.0%}"),
            ("利润率", f"{node.profit_margin:+.1%}"),
            ("韧性", f"{node.resilience_score:.1f}"),
        ]
        for col, (label, value) in enumerate(row1):
            grid.addWidget(self._make_metric_tile(label, value), 1, col)

        card.add_layout(grid)
        return card

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
            ReportExporter.export_markdown(self._report, path)
