"""结果分析页

Day 1 版：占位页面。
后续迭代：策略对比曲线图、雷达图、关键事件时间线、Agent 发言摘录。
"""
from PySide6.QtWidgets import QWidget
from prism.ui.widgets import PlaceholderPage


class ResultPage(PlaceholderPage):
    """仿真结果分析"""

    def __init__(self, parent=None):
        super().__init__(
            title="结果分析",
            description="此处展示仿真结果。\n包括策略对比热度/情绪曲线、六维雷达图评估、\n关键事件时间线与 Agent 发言摘录。",
            parent=parent,
        )
