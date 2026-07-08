"""仿真运行页

Day 1 版：占位页面。
后续迭代：启动/暂停/中止控制、实时轮次进度、Agent 发言流、仿真状态展示。
"""
from PySide6.QtWidgets import QWidget
from prism.ui.widgets import PlaceholderPage


class SimulationPage(PlaceholderPage):
    """多智能体仿真运行"""

    def __init__(self, parent=None):
        super().__init__(
            title="仿真运行",
            description="在此启动和控制多智能体仿真。\n"
            "8 个固定类型 Agent 将在 8~12 轮中模拟舆论演化，\n"
            "实时显示发言流、热度曲线和关键事件。",
            parent=parent,
        )
