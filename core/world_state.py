"""世界状态数据模型

WorldState 记录仿真的全局状态快照。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentSnapshot:
    """单个行为体在某轮的快照"""
    agent_id: int
    pressure: float = 0.0           # 压力/焦虑水平 0~1
    decision_stance: str = ""       # 决策倾向：aggressive/cautious/cooperative/defensive
    spoke: bool = False             # 本轮是否激活
    speech: str = ""                # 响应/发言内容
    decision_summary: str = ""      # 本轮决策摘要


@dataclass
class NodeState:
    """供应链节点的细粒度状态"""
    name: str
    node_type: str
    inventory: float = 0.0
    capacity: float = 0.0
    lead_time: float = 0.0
    cost_index: float = 50.0
    service_level: float = 0.85
    profit_margin: float = 0.15
    resilience_score: float = 60.0


@dataclass
class KeyEvent:
    """仿真过程中的关键事件"""
    round: int
    simulated_hour: int
    event_type: str                 # 事件类型标识
    description: str                # 事件描述
    inventory_delta: float = 0.0
    cost_delta: float = 0.0
    delay_delta: float = 0.0
    service_delta: float = 0.0
    margin_delta: float = 0.0


@dataclass
class WorldState:
    """仿真世界的全局状态"""
    round: int = 0
    simulated_hour: int = 0             # 累计模拟周期
    inventory_level: float = 75.0       # 全链库存水平 0~100
    cost_index: float = 50.0            # 成本指数 0~100
    delivery_delay: float = 0.0         # 平均交付延迟（周期数）
    service_level: float = 0.85         # 订单满足率 0~1
    profit_margin: float = 0.15         # 全链利润率 -1~1
    resilience_score: float = 60.0      # 韧性评分 0~100
    key_events: list[KeyEvent] = field(default_factory=list)
    agent_states: dict[int, AgentSnapshot] = field(default_factory=dict)
    node_states: list[NodeState] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "simulated_hour": self.simulated_hour,
            "inventory_level": self.inventory_level,
            "cost_index": self.cost_index,
            "delivery_delay": self.delivery_delay,
            "service_level": self.service_level,
            "profit_margin": self.profit_margin,
            "resilience_score": self.resilience_score,
            "key_events": [
                {
                    "round": e.round,
                    "simulated_hour": e.simulated_hour,
                    "event_type": e.event_type,
                    "description": e.description,
                    "inventory_delta": e.inventory_delta,
                    "cost_delta": e.cost_delta,
                    "delay_delta": e.delay_delta,
                    "service_delta": e.service_delta,
                    "margin_delta": e.margin_delta,
                }
                for e in self.key_events
            ],
            "agent_states": {
                str(aid): {
                    "agent_id": s.agent_id,
                    "pressure": s.pressure,
                    "decision_stance": s.decision_stance,
                    "spoke": s.spoke,
                    "speech": s.speech,
                    "decision_summary": s.decision_summary,
                }
                for aid, s in self.agent_states.items()
            },
            "node_states": [
                {
                    "name": node.name,
                    "node_type": node.node_type,
                    "inventory": node.inventory,
                    "capacity": node.capacity,
                    "lead_time": node.lead_time,
                    "cost_index": node.cost_index,
                    "service_level": node.service_level,
                    "profit_margin": node.profit_margin,
                    "resilience_score": node.resilience_score,
                }
                for node in self.node_states
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldState:
        simulated_hour = data.get("simulated_hour", 0)
        state = cls(
            round=data["round"],
            simulated_hour=simulated_hour,
            inventory_level=data["inventory_level"],
            cost_index=data["cost_index"],
            delivery_delay=data["delivery_delay"],
            service_level=data.get("service_level", 0.85),
            profit_margin=data.get("profit_margin", 0.15),
            resilience_score=data.get("resilience_score", 60.0),
        )
        state.key_events = [
            KeyEvent(
                round=e["round"],
                simulated_hour=e["simulated_hour"],
                event_type=e["event_type"],
                description=e["description"],
                inventory_delta=e.get("inventory_delta", 0.0),
                cost_delta=e.get("cost_delta", 0.0),
                delay_delta=e.get("delay_delta", 0.0),
                service_delta=e.get("service_delta", 0.0),
                margin_delta=e.get("margin_delta", 0.0),
            )
            for e in data.get("key_events", [])
        ]
        state.agent_states = {
            int(aid): AgentSnapshot(
                agent_id=s["agent_id"],
                pressure=s.get("pressure", 0.0),
                decision_stance=s.get("decision_stance", ""),
                spoke=s.get("spoke", False),
                speech=s.get("speech", ""),
                decision_summary=s.get("decision_summary", ""),
            )
            for aid, s in data.get("agent_states", {}).items()
        }
        state.node_states = [
            NodeState(
                name=node.get("name", ""),
                node_type=node.get("node_type", ""),
                inventory=node.get("inventory", 0.0),
                capacity=node.get("capacity", 0.0),
                lead_time=node.get("lead_time", 0.0),
                cost_index=node.get("cost_index", 50.0),
                service_level=node.get("service_level", 0.85),
                profit_margin=node.get("profit_margin", 0.15),
                resilience_score=node.get("resilience_score", 60.0),
            )
            for node in data.get("node_states", [])
        ]
        return state
