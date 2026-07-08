"""pyqtgraph 图表封装

策略对比曲线图、雷达图等可视化组件的统一封装。
Day 1 版：定义接口。
后续迭代：实现具体图表。
"""
from __future__ import annotations

from typing import List


class PrismChart:
    """图表基类"""

    def __init__(self):
        self._widget = None

    def widget(self):
        """返回实际的 QWidget（后续接入 pyqtgraph）"""
        return self._widget


class HeatCurveChart(PrismChart):
    """热度 / 情绪 / 支持率 双策略叠加曲线图"""

    def set_data(
        self,
        strategy_a_label: str,
        strategy_a_heats: List[float],
        strategy_a_sentiments: List[float],
        strategy_b_label: str = "",
        strategy_b_heats: List[float] | None = None,
        strategy_b_sentiments: List[float] | None = None,
    ):
        """设置图表数据（后续实现）"""
        pass


class RadarChart(PrismChart):
    """六维策略评估雷达图"""

    def set_data(
        self,
        labels: List[str],
        strategy_a_scores: List[float],
        strategy_b_scores: List[float],
        strategy_a_label: str = "策略 A",
        strategy_b_label: str = "策略 B",
    ):
        """设置雷达图数据（后续实现）"""
        pass
