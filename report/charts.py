"""pyqtgraph 图表封装

供应链指标曲线图、雷达图等可视化组件的统一封装。
"""
from __future__ import annotations


class PrismChart:
    """图表基类"""

    def __init__(self):
        self._widget = None

    def widget(self):
        """返回实际的 QWidget（后续接入 pyqtgraph）"""
        return self._widget


class SupplyChainCurveChart(PrismChart):
    """库存 / 成本 / 交付延迟 / 服务水平 双方案叠加曲线图"""

    def set_data(
        self,
        strategy_a_label: str,
        strategy_a_inventories: list[float],
        strategy_a_costs: list[float],
        strategy_a_delays: list[float],
        strategy_b_label: str = "",
        strategy_b_inventories: list[float] | None = None,
        strategy_b_costs: list[float] | None = None,
        strategy_b_delays: list[float] | None = None,
    ):
        """设置图表数据（后续实现）"""
        pass


class RadarChart(PrismChart):
    """六维方案评估雷达图"""

    def set_data(
        self,
        labels: list[str],
        strategy_a_scores: list[float],
        strategy_b_scores: list[float],
        strategy_a_label: str = "方案 A",
        strategy_b_label: str = "方案 B",
    ):
        """设置雷达图数据（后续实现）"""
        pass
