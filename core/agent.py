"""Agent 数据模型

使用 @dataclass + to_dict/from_dict 序列化。

7 个供应链行为体模板定义见 docs/prism.md §6.1。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Agent:
    """仿真行为体数据模型"""

    id: int
    name: str
    role: str                              # 角色标签
    decision_stance: str                   # 决策倾向：aggressive/cautious/cooperative/defensive
    base_stance: str                       # 初始倾向（用于复位）
    influence: float                       # 单次决策对世界状态的影响力权重
    activity: float                        # 每轮被激活的概率（0~1）
    pressure: float = 0.0                  # 当前压力水平（0~1）
    capacity: float = 1.0                  # 产能利用率（0~1）
    active_cycles: list[int] = field(default_factory=list)  # 活跃周期
    profile: str = ""                      # 角色画像（System Prompt）
    memory: list[str] = field(default_factory=list)         # 最近 N 轮记忆摘要

    def reset(self):
        """复位到初始倾向和状态"""
        self.decision_stance = self.base_stance
        self.pressure = 0.0
        self.capacity = 1.0
        self.memory.clear()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "decision_stance": self.decision_stance,
            "base_stance": self.base_stance,
            "influence": self.influence,
            "activity": self.activity,
            "pressure": self.pressure,
            "capacity": self.capacity,
            "active_cycles": self.active_cycles,
            "profile": self.profile,
            "memory": self.memory,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Agent:
        return cls(
            id=data["id"],
            name=data["name"],
            role=data["role"],
            decision_stance=data["decision_stance"],
            base_stance=data["base_stance"],
            influence=data["influence"],
            activity=data["activity"],
            pressure=data.get("pressure", 0.0),
            capacity=data.get("capacity", 1.0),
            active_cycles=data.get("active_cycles", []),
            profile=data["profile"],
            memory=data.get("memory", []),
        )


# ============================================================
# 7 个固定供应链行为体模板
# ============================================================

AGENT_TEMPLATES: list[dict] = [
    {
        "id": 1,
        "name": "原材料供应商",
        "role": "上游供应商",
        "decision_stance": "cautious",
        "influence": 1.0,
        "activity": 0.5,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你是一家原材料供应商。你关注原材料价格波动、订单稳定性和下游需求变化。"
            "你的决策倾向偏保守（cautious），倾向于维持安全库存，在需求不确定时会减少供应承诺。"
            "当成本上升或下游延迟付款时，你的压力会增加，可能进一步收紧供应。"
        ),
    },
    {
        "id": 2,
        "name": "制造商",
        "role": "核心制造商",
        "decision_stance": "cooperative",
        "influence": 2.5,
        "activity": 0.9,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你是一家核心制造商，处于供应链的中心位置。你负责协调上下游，管理产能与排产决策。"
            "你的决策倾向偏协作（cooperative），倾向于与上下游协商解决问题。"
            "当原材料短缺或订单积压时，你的压力会上升。你的影响力最大，决策会影响整条供应链。"
        ),
    },
    {
        "id": 3,
        "name": "分销商",
        "role": "中游分销商",
        "decision_stance": "cautious",
        "influence": 1.5,
        "activity": 0.6,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你是一家区域分销商，承担库存缓冲角色。你受需求波动冲击较大。"
            "你的决策倾向偏保守（cautious），倾向于根据下游订单调整库存策略。"
            "当库存过高或下游需求疲软时，你的压力会增大，可能减少向制造商的采购量。"
        ),
    },
    {
        "id": 4,
        "name": "零售商",
        "role": "下游零售商",
        "decision_stance": "aggressive",
        "influence": 1.8,
        "activity": 0.8,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你是一家终端零售商，直面消费者。你对价格和库存最敏感。"
            "你的决策倾向偏激进（aggressive），倾向于通过促销或降价维持市场份额。"
            "当库存积压或竞争对手降价时，你的压力会上升，可能发起价格战或紧急补货。"
        ),
    },
    {
        "id": 5,
        "name": "物流服务商",
        "role": "物流支撑方",
        "decision_stance": "cooperative",
        "influence": 1.2,
        "activity": 0.5,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你是一家第三方物流服务商。运输时效与成本是你关注的关键变量。"
            "你的决策倾向偏协作（cooperative），倾向于根据运力情况调整服务承诺。"
            "当运力紧张或成本上升时，你的压力会增大，可能延迟交付或提高运费。"
        ),
    },
    {
        "id": 6,
        "name": "消费者",
        "role": "终端消费者",
        "decision_stance": "aggressive",
        "influence": 2.0,
        "activity": 0.7,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你代表终端消费者群体。你的购买行为受价格与服务水平直接影响。"
            "你的决策倾向偏激进（aggressive），对价格和服务变化反应迅速。"
            "当价格上涨或服务水平下降时，你会减少购买或转向替代产品。"
            "当促销活动出现时，需求可能激增。"
        ),
    },
    {
        "id": 7,
        "name": "监管机构",
        "role": "外部监管方",
        "decision_stance": "defensive",
        "influence": 2.0,
        "activity": 0.2,
        "active_cycles": list(range(1, 13)),
        "profile": (
            "你代表政府监管机构。你仅对合规与安全事件做出反应。"
            "你的决策倾向偏防御（defensive），关注全链合规性和安全风险。"
            "当出现质量安全、环境违规或市场失序信号时，你会介入调查并施加监管压力。"
            "正常情况下你保持沉默，不影响供应链运行。"
        ),
    },
]
