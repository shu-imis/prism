"""行为体发言的文本规范化（兼容层）。

实现已下沉到 core.text_utils（报告导出等后端路径共用），
此处保留导入路径以兼容既有 UI 引用。
"""
from core.text_utils import normalize_speech

__all__ = ["normalize_speech"]
