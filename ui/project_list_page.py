"""历史项目列表页

Day 1 版：占位页面，展示空状态。
后续迭代：项目列表（名称、创建时间、最近仿真状态）、快捷操作（继续/删除）。
"""
from PySide6.QtWidgets import QWidget
from prism.ui.widgets import PlaceholderPage


class ProjectListPage(PlaceholderPage):
    """历史项目列表"""

    def __init__(self, parent=None):
        super().__init__(
            title="历史项目",
            description="此处将展示您所有的推演项目记录。\n包括项目名称、创建时间、最近一次仿真状态，以及继续或删除操作。",
            parent=parent,
        )
