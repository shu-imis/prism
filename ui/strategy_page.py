"""策略配置页

Day 1 版：占位页面。
后续迭代：2~4 种回应策略配置、声明稿、发布时间偏移、策略对比预览。
"""
from PySide6.QtWidgets import QWidget
from prism.ui.widgets import PlaceholderPage


class StrategyPage(PlaceholderPage):
    """回应策略配置"""

    def __init__(self, parent=None):
        super().__init__(
            title="策略配置",
            description="配置 2~4 种回应策略。\n每种策略包含名称、声明稿全文、计划发布时间，支持并排对比预览差异。",
            parent=parent,
        )
