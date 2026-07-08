"""世界状态数据模型

WorldState 记录仿真的全局状态快照。
参考 MiroFish 的 SimulationRunState 分层设计。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class AgentSnapshot:
    """单个 Agent 在某轮的快照"""
    agent_id: int
    emotion: float
    trust: float
    stance: str
    spoke: bool = False            # 本轮是否发言
    speech: str = ""               # 发言内容


@dataclass
class KeyEvent:
    """仿真过程中的关键事件"""
    round: int
    simulated_hour: int
    event_type: str                # 事件类型标识
    description: str               # 事件描述
    heat_delta: float = 0.0
    sentiment_delta: float = 0.0
    trust_delta: float = 0.0


@dataclass
class WorldState:
    """仿真世界的全局状态"""
    round: int = 0
    simulated_hour: int = 0        # 累计模拟小时
    heat: float = 0.0              # 热度（0~100）
    sentiment: float = 0.0         # 整体情绪（-1.0 ~ 1.0）
    support_rate: float = 0.5      # 企业支持率（0~1）
    key_events: List[KeyEvent] = field(default_factory=list)
    agent_states: Dict[int, AgentSnapshot] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "simulated_hour": self.simulated_hour,
            "heat": self.heat,
            "sentiment": self.sentiment,
            "support_rate": self.support_rate,
            "key_events": [
                {
                    "round": e.round,
                    "simulated_hour": e.simulated_hour,
                    "event_type": e.event_type,
                    "description": e.description,
                    "heat_delta": e.heat_delta,
                    "sentiment_delta": e.sentiment_delta,
                    "trust_delta": e.trust_delta,
                }
                for e in self.key_events
            ],
            "agent_states": {
                str(aid): {
                    "agent_id": s.agent_id,
                    "emotion": s.emotion,
                    "trust": s.trust,
                    "stance": s.stance,
                    "spoke": s.spoke,
                    "speech": s.speech,
                }
                for aid, s in self.agent_states.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldState:
        state = cls(
            round=data["round"],
            simulated_hour=data["simulated_hour"],
            heat=data["heat"],
            sentiment=data["sentiment"],
            support_rate=data["support_rate"],
        )
        state.key_events = [
            KeyEvent(**e) for e in data.get("key_events", [])
        ]
        state.agent_states = {
            int(aid): AgentSnapshot(**s)
            for aid, s in data.get("agent_states", {}).items()
        }
        return state
