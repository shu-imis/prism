"""Prism — 供应链决策推演工具"""
__version__ = "0.1.0"

from typing import Any


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    """将值限制在 [lower, upper] 范围内。"""
    return max(lower, min(upper, value))


def clamp_float(value: Any, lower: float, upper: float) -> float:
    """安全地将任意值解析为 float 并限制范围内。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return clamp(parsed, lower, upper)
