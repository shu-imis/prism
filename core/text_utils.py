"""行为体发言的文本规范化。

LLM 输出的标点中英文混杂、句末标点有无不一，
展示与导出前统一为中文标点并补齐句末句号（不改变语义）。
"""
from __future__ import annotations

import re

_CJK = r"[一-鿿]"
# 标点转全角的左邻字符：CJK 或常见中文闭符号（闭引号/书名号/括号收尾）
_CJK_OR_CLOSE = r"[一-鿿」”』》）】]"
# 句末豁免集合：已有终止标点或闭符号结尾时不补句号
_TERMINAL_PUNCT = "。！？!?…"
_CLOSING_PUNCT = "」”』》）】"


def normalize_speech(text: str) -> str:
    """规范化发言标点。

    - CJK 字符（或中文闭符号）后的半角逗号/分号/问号/叹号/冒号 → 全角（冒号后限非数字，避免误伤时间）
    - 句末半角句号 → 全角；句末无终止标点/闭符号 → 补「。」
    - 不含 CJK 的文本原样返回
    """
    text = (text or "").strip()
    if not text:
        return text
    # 纯英文/无 CJK 文本不做任何处理
    if not re.search(_CJK, text):
        return text
    text = re.sub(rf"(?<={_CJK_OR_CLOSE}),", "，", text)
    text = re.sub(rf"(?<={_CJK_OR_CLOSE});", "；", text)
    text = re.sub(rf"(?<={_CJK_OR_CLOSE})\?", "？", text)
    text = re.sub(rf"(?<={_CJK_OR_CLOSE})!", "！", text)
    text = re.sub(rf"(?<={_CJK_OR_CLOSE}):(?!\d)", "：", text)
    # 结尾三连点归一为中文省略号（…已在终止标点中），避免 "..." 被改成 "..。" 畸形
    if text.endswith("..."):
        text = text[:-3] + "…"
    if text.endswith("."):
        text = text[:-1] + "。"
    if text[-1] not in _TERMINAL_PUNCT and text[-1] not in _CLOSING_PUNCT:
        text += "。"
    return text
