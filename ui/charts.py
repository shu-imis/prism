"""QPainter 图表组件 — 指标演化折线图与六维评估雷达图。

遵循设计系统：无圆角、细线、JetBrains Mono 数字、调色板取色。
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.agent import AGENT_TEMPLATES
from core.text_utils import normalize_speech
from ui.styles import (
    ACCENT,
    BORDER_LIGHT,
    CHART_BLUE,
    CHART_DARK,
    CHART_GREEN,
    CHART_NEUTRAL,
    CHART_ORANGE,
    CHART_PURPLE,
    CHART_RED,
    CHART_TEAL,
    COLOR_RED,
    PAD_MD,
    PAD_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# 折线图的指标系列：字段名、颜色、图例格式化（统一取色自数据可视化色板）
_SERIES = [
    ("inventory_level", CHART_BLUE, "库存", "{:.0f}"),
    ("cost_index", CHART_ORANGE, "成本", "{:.0f}"),
    ("service_level", CHART_GREEN, "服务水平", "{:.0%}"),
    ("profit_margin", CHART_PURPLE, "利润率", "{:+.0%}"),
    ("delivery_delay", CHART_RED, "交付延迟", "{:.1f}"),
]


class MetricsChart(QWidget):
    """多指标演化折线图（各系列按自身取值范围归一化）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rounds = []
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_rounds(self, rounds):
        self._rounds = list(rounds or [])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._rounds:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无轮次数据")
            painter.end()
            return

        w, h = self.width(), self.height()
        top, bottom, left, right = 30, h - 20, 36, 12
        n = len(self._rounds)

        def x_at(i):
            return left + (w - left - right) * (i / max(n - 1, 1))

        # 横向网格线
        painter.setPen(QColor(BORDER_LIGHT))
        for i in range(4):
            y = top + (bottom - top) * i / 3
            painter.drawLine(left, int(y), w - right, int(y))

        mono = QFont("JetBrains Mono")
        mono.setPixelSize(10)

        # 系列折线与数据点
        for field, color, _label, _fmt in _SERIES:
            values = [float(getattr(r, field)) for r in self._rounds]
            lo, hi = min(values), max(values)
            span = (hi - lo) or 1.0
            points = [
                QPointF(x_at(i), bottom - (v - lo) / span * (bottom - top))
                for i, v in enumerate(values)
            ]
            painter.setPen(QPen(QColor(color), 2))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            for pt in points:
                painter.drawEllipse(pt, 2.5, 2.5)

        # X 轴周期标签
        painter.setFont(mono)
        painter.setPen(QColor(TEXT_MUTED))
        step = 1 if n <= 12 else 2
        for i, state in enumerate(self._rounds):
            if i % step:
                continue
            painter.drawText(
                QRectF(x_at(i) - 20, bottom + 4, 40, 14),
                Qt.AlignCenter,
                str(state.round),
            )

        # 图例：色点 + 指标名 + 末值
        painter.setFont(mono)
        cursor = left
        y = 14
        for field, color, label, fmt in _SERIES:
            last = float(getattr(self._rounds[-1], field))
            text = f"{label} {fmt.format(last)}"
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(cursor + 4, y), 3, 3)
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(QRectF(cursor + 12, y - 7, 120, 14), Qt.AlignLeft, text)
            cursor += 12 + painter.fontMetrics().horizontalAdvance(text) + 18

        painter.end()


class RadarChart(QWidget):
    """六维评估雷达图（0~100 六轴）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scores: dict[str, float] = {}
        self.setFixedHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_scores(self, scores: dict):
        self._scores = dict(scores or {})
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._scores:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无评估数据")
            painter.end()
            return

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 4
        radius = min(w, h) / 2 - 34
        dims = list(self._scores.keys())
        n = len(dims)

        def vertex(i, ratio):
            angle = -math.pi / 2 + 2 * math.pi * i / n
            return QPointF(
                cx + radius * ratio * math.cos(angle),
                cy + radius * ratio * math.sin(angle),
            )

        # 网格环（25/50/75/100）
        for ratio in (0.25, 0.5, 0.75, 1.0):
            painter.setPen(QPen(QColor(BORDER_LIGHT), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF([vertex(i, ratio) for i in range(n)]))
        # 轴线
        painter.setPen(QPen(QColor(BORDER_LIGHT), 1))
        for i in range(n):
            painter.drawLine(QPointF(cx, cy), vertex(i, 1.0))

        # 数值多边形
        values = [max(0.0, min(100.0, float(self._scores[d]))) / 100 for d in dims]
        polygon = QPolygonF([vertex(i, v) for i, v in enumerate(values)])
        fill = QColor(ACCENT)
        fill.setAlpha(50)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.drawPolygon(polygon)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ACCENT))
        for pt in polygon:
            painter.drawEllipse(pt, 3, 3)

        # 轴标签（名称 + 分值）
        label_font = QFont()
        label_font.setPixelSize(11)
        painter.setFont(label_font)
        for i, dim in enumerate(dims):
            pt = vertex(i, 1.0)
            dx, dy = pt.x() - cx, pt.y() - cy
            lx = pt.x() + (26 * dx / radius if dx else 0)
            ly = pt.y() + (18 * dy / radius if dy else 0)
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(
                QRectF(lx - 60, ly - 16, 120, 14), Qt.AlignCenter, dim
            )
            painter.setPen(QColor(TEXT_PRIMARY))
            painter.drawText(
                QRectF(lx - 60, ly - 1, 120, 13),
                Qt.AlignCenter,
                str(int(self._scores[dim])),
            )

        painter.end()


# ============================================================
# 演化泳道图：行为体 × 周期的行动色块矩阵
# ============================================================

# 行动类型 → 色块颜色（统一取色自数据可视化色板；
# 不用橙（与品牌金相近）、维持用中性灰空色以突出主动行动）
ACTION_COLORS = {
    "maintain": CHART_NEUTRAL,
    "adjust_supply": CHART_BLUE,
    "adjust_price": ACCENT,
    "adjust_capacity": CHART_TEAL,
    "expedite_logistics": CHART_GREEN,
    "reduce_orders": CHART_RED,
    "shift_demand": CHART_PURPLE,
    "intervene": CHART_DARK,
}

ACTION_LABELS = {
    "maintain": "维持",
    "adjust_supply": "调供应",
    "adjust_price": "调价",
    "adjust_capacity": "调产能",
    "expedite_logistics": "物流加急",
    "reduce_orders": "减订单",
    "shift_demand": "需求转移",
    "intervene": "监管介入",
}

_CELL_H = 20


class SwimlaneGrid(QWidget):
    """7 行为体 × N 周期的行动色块矩阵，悬停显示行动详情。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(PAD_SM)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_rounds(self, rounds):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setVisible(False)
                item.widget().deleteLater()
            elif item.layout():
                self._clear(item.layout())
        rounds = [r for r in (rounds or []) if r.round > 0]  # 跳过初始状态轮
        if not rounds:
            return

        event_rounds = {
            state.round for state in rounds for _ in state.key_events
        }

        grid = QGridLayout()
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)

        mono = QFont("JetBrains Mono")
        mono.setPixelSize(9)

        # 表头：周期序号（有关键事件的周期标红）
        # 格宽自适应：周期列均分可用宽度（24~56px），任意周期数都不溢出
        for col, state in enumerate(rounds, start=1):
            header = QLabel(str(state.round))
            header.setFont(mono)
            has_event = state.round in event_rounds
            header.setStyleSheet(
                f"color:{COLOR_RED if has_event else TEXT_MUTED};"
            )
            header.setAlignment(Qt.AlignCenter)
            header.setFixedHeight(14)
            header.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            if has_event:
                header.setToolTip("该周期触发关键事件")
            grid.addWidget(header, 0, col)
            grid.setColumnStretch(col, 1)

        # 每个行为体一行
        for row, tmpl in enumerate(AGENT_TEMPLATES, start=1):
            name = QLabel(tmpl["name"])
            name.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};")
            name.setFixedWidth(76)  # 最长名「原材料供应商」6 字需 ~70px
            grid.addWidget(name, row, 0)
            for col, state in enumerate(rounds, start=1):
                snapshot = state.agent_states.get(tmpl["id"])
                cell = QLabel("")
                cell.setFixedHeight(_CELL_H)
                cell.setMinimumWidth(24)
                cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                action = snapshot.action_type if snapshot else ""
                summary = (
                    (snapshot.decision_summary or snapshot.speech)
                    if snapshot and snapshot.spoke else ""
                )
                if snapshot and snapshot.spoke and action:
                    color = ACTION_COLORS.get(action, "#E3E3DD")
                    cell.setStyleSheet(f"background:{color};")
                    label = ACTION_LABELS.get(action, action)
                    tip = f"周期 {state.round} · {tmpl['name']}【{label}】"
                    if summary:
                        tip += f"\n{normalize_speech(summary)}"
                    cell.setToolTip(tip)
                else:
                    cell.setStyleSheet("background:transparent;")
                grid.addWidget(cell, row, col)

        self._layout.addLayout(grid)

        # 图例
        legend = QHBoxLayout()
        legend.setSpacing(PAD_MD)
        for action, color in ACTION_COLORS.items():
            dot = QLabel("■")
            dot.setStyleSheet(f"color:{color};font-size:10px;")
            legend.addWidget(dot)
            text = QLabel(ACTION_LABELS[action])
            text.setStyleSheet(f"font-size:10px;color:{TEXT_MUTED};")
            legend.addWidget(text)
        legend.addStretch()
        self._layout.addLayout(legend)

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setVisible(False)
                item.widget().deleteLater()
            elif item.layout():
                SwimlaneGrid._clear(item.layout())
