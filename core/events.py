"""关键事件定义与检测规则

6 种关键事件类型，触发条件与影响见 §6.6。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List
from prism.core.world_state import WorldState, KeyEvent


class EventType(str, Enum):
    """关键事件类型"""
    MEDIA_FOLLOW_UP = "media_follow_up"       # 媒体跟进报道
    REGULATORY_SIGNAL = "regulatory_signal"    # 监管介入信号
    COMPETITOR_ATTACK = "competitor_attack"    # 竞品借势攻击
    INSIDER_LEAK = "insider_leak"             # 内部员工爆料
    TRENDING_TOP = "trending_top"             # 话题登顶热搜
    NATURAL_COOLING = "natural_cooling"       # 舆情自然降温


# 事件模板
EVENT_TEMPLATES: dict[EventType, dict] = {
    EventType.MEDIA_FOLLOW_UP: {
        "description": "媒体跟进报道",
        "heat_delta": 10.0,
        "sentiment_delta": -0.15,
        "trust_delta": 0.0,
    },
    EventType.REGULATORY_SIGNAL: {
        "description": "监管介入信号",
        "heat_delta": 15.0,
        "sentiment_delta": 0.0,
        "trust_delta": -0.1,
    },
    EventType.COMPETITOR_ATTACK: {
        "description": "竞品借势攻击",
        "heat_delta": 5.0,
        "sentiment_delta": -0.1,
        "trust_delta": 0.0,
    },
    EventType.INSIDER_LEAK: {
        "description": "内部员工爆料",
        "heat_delta": 20.0,
        "sentiment_delta": 0.0,
        "trust_delta": 0.0,
    },
    EventType.TRENDING_TOP: {
        "description": "话题登顶热搜",
        "heat_delta": 10.0,
        "sentiment_delta": 0.0,
        "trust_delta": 0.0,
    },
    EventType.NATURAL_COOLING: {
        "description": "舆情自然降温",
        "heat_delta": -5.0,
        "sentiment_delta": 0.05,
        "trust_delta": 0.0,
    },
}


class EventDetector:
    """关键事件检测器"""

    def __init__(self):
        self._consecutive_cooling = 0  # 连续无事件轮次计数

    def detect(
        self,
        state: WorldState,
        kol_spoke: bool = False,
        kol_speech: str = "",
        regulator_spoke: bool = False,
        regulator_speech: str = "",
        competitor_spoke: bool = False,
    ) -> List[KeyEvent]:
        """检测本轮触发的关键事件"""
        events: List[KeyEvent] = []

        # 1. 媒体跟进报道
        if (
            state.heat > 60
            and kol_spoke
            and any(kw in kol_speech for kw in ["调查", "进一步", "揭露", "真相", "内幕"])
        ):
            events.append(self._make_event(state, EventType.MEDIA_FOLLOW_UP))

        # 2. 监管介入信号
        if (
            regulator_spoke
            and any(kw in regulator_speech for kw in ["合规", "监管", "调查", "法规"])
        ):
            events.append(self._make_event(state, EventType.REGULATORY_SIGNAL))

        # 3. 竞品借势攻击
        if state.heat > 50 and competitor_spoke:
            events.append(self._make_event(state, EventType.COMPETITOR_ATTACK))

        # 4. 内部员工爆料（5% 概率，heat > 40）
        if state.heat > 40:
            import random
            if random.random() < 0.05:
                events.append(self._make_event(state, EventType.INSIDER_LEAK))

        # 5. 话题登顶热搜
        if state.heat > 80:
            events.append(self._make_event(state, EventType.TRENDING_TOP))

        # 6. 舆情自然降温
        if len(events) == 0:
            self._consecutive_cooling += 1
            if state.heat > 30 and self._consecutive_cooling >= 3:
                events.append(self._make_event(state, EventType.NATURAL_COOLING))
                self._consecutive_cooling = 0
        else:
            self._consecutive_cooling = 0

        return events

    def _make_event(self, state: WorldState, event_type: EventType) -> KeyEvent:
        t = EVENT_TEMPLATES[event_type]
        return KeyEvent(
            round=state.round,
            simulated_hour=state.simulated_hour,
            event_type=event_type.value,
            description=t["description"],
            heat_delta=t["heat_delta"],
            sentiment_delta=t["sentiment_delta"],
            trust_delta=t["trust_delta"],
        )
