"""关键事件定义与检测规则

5 种供应链关键事件类型，触发条件与影响见 docs/prism.md §6.4。
"""
from __future__ import annotations

from enum import Enum
from core.world_state import WorldState, KeyEvent


class EventType(str, Enum):
    """关键事件类型"""
    RAW_MATERIAL_SHORTAGE = "raw_material_shortage"       # 原材料断供
    WAREHOUSE_OVERFLOW = "warehouse_overflow"              # 仓储爆仓
    PRICE_WAR = "price_war"                                # 价格战触发
    REGULATORY_INTERVENTION = "regulatory_intervention"    # 监管介入
    DEMAND_SURGE = "demand_surge"                          # 需求激增


# 事件模板
EVENT_TEMPLATES: dict[EventType, dict] = {
    EventType.RAW_MATERIAL_SHORTAGE: {
        "description": "原材料断供",
        "inventory_delta": -20.0,
        "cost_delta": 15.0,
        "delay_delta": 2.0,
        "service_delta": -0.05,
        "margin_delta": -0.08,
    },
    EventType.WAREHOUSE_OVERFLOW: {
        "description": "仓储爆仓",
        "inventory_delta": 0.0,
        "cost_delta": 10.0,
        "delay_delta": -1.0,
        "service_delta": 0.0,
        "margin_delta": -0.03,
    },
    EventType.PRICE_WAR: {
        "description": "价格战触发",
        "inventory_delta": -5.0,
        "cost_delta": 0.0,
        "delay_delta": 0.0,
        "service_delta": 0.05,
        "margin_delta": -0.05,
    },
    EventType.REGULATORY_INTERVENTION: {
        "description": "监管介入",
        "inventory_delta": 0.0,
        "cost_delta": 15.0,
        "delay_delta": 1.0,
        "service_delta": -0.03,
        "margin_delta": -0.10,
    },
    EventType.DEMAND_SURGE: {
        "description": "需求激增",
        "inventory_delta": -15.0,
        "cost_delta": 0.0,
        "delay_delta": 1.5,
        "service_delta": -0.08,
        "margin_delta": 0.05,
    },
}


class EventDetector:
    """关键事件检测器"""

    def __init__(self):
        self._supplier_delay_count = 0       # 供应商连续延迟计数
        self._regulator_risk_count = 0       # 监管机构连续标记风险计数

    def detect(
        self,
        state: WorldState,
        supplier_delayed: bool = False,
        retailer_margin_negative: bool = False,
        regulator_risk_flagged: bool = False,
        demand_surge_detected: bool = False,
    ) -> list[KeyEvent]:
        """检测本轮触发的关键事件"""
        events: list[KeyEvent] = []

        # 1. 原材料断供
        if supplier_delayed:
            self._supplier_delay_count += 1
        else:
            self._supplier_delay_count = 0
        if self._supplier_delay_count >= 2:
            events.append(self._make_event(state, EventType.RAW_MATERIAL_SHORTAGE))
            self._supplier_delay_count = 0

        # 2. 仓储爆仓（库存 > 90 视为爆仓风险）
        if state.inventory_level > 90:
            events.append(self._make_event(state, EventType.WAREHOUSE_OVERFLOW))

        # 3. 价格战触发（零售商利润率为负）
        if retailer_margin_negative and state.profit_margin < 0:
            events.append(self._make_event(state, EventType.PRICE_WAR))

        # 4. 监管介入
        if regulator_risk_flagged:
            self._regulator_risk_count += 1
        else:
            self._regulator_risk_count = 0
        if self._regulator_risk_count >= 2:
            events.append(self._make_event(state, EventType.REGULATORY_INTERVENTION))
            self._regulator_risk_count = 0

        # 5. 需求激增（由调用方判断，传入标志）
        if demand_surge_detected:
            events.append(self._make_event(state, EventType.DEMAND_SURGE))

        return events

    def _make_event(self, state: WorldState, event_type: EventType) -> KeyEvent:
        t = EVENT_TEMPLATES[event_type]
        return KeyEvent(
            round=state.round,
            simulated_hour=state.simulated_hour,
            event_type=event_type.value,
            description=t["description"],
            inventory_delta=t["inventory_delta"],
            cost_delta=t["cost_delta"],
            delay_delta=t["delay_delta"],
            service_delta=t["service_delta"],
            margin_delta=t["margin_delta"],
        )
