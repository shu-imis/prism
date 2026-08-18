"""Prism — 供应链决策推演工具"""

from typing import Any


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    """将值限制在 [lower, upper] 范围内。"""
    return max(lower, min(upper, value))


def clamp_float(
    value: Any,
    lower: float,
    upper: float,
    default: float = 0.0,
) -> float:
    """安全地将任意值解析为 float 并限制范围内；解析失败返回 default。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return clamp(parsed, lower, upper)


def clamp_int(value: Any, lower: int, upper: int, default: int) -> int:
    """安全地将任意值解析为 int 并限制范围内；解析失败返回 default。"""
    try:
        return max(lower, min(upper, int(float(value))))
    except (TypeError, ValueError, OverflowError):  # OverflowError: int(float("inf"))
        return default