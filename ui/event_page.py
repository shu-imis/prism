"""事件录入页

Day 1 版：占位页面。
后续迭代：事件标题、涉及行业、背景描述、企业声明、初始热度/情绪滑块。
"""
from PySide6.QtWidgets import QWidget
from ui.widgets import PlaceholderPage


class EventPage(PlaceholderPage):
    """危机事件录入"""

    def __init__(self, parent=None):
        super().__init__(
            title="事件录入",
            description="在此录入危机事件详情。\n包括事件标题、涉及行业、事件背景描述、企业现有声明稿、以及初始热度与公众情绪基线。",
            parent=parent,
        )
