"""Agent 数据模型

参考 MiroFish 的 OasisAgentProfile + AgentActivityConfig 模式，
使用 @dataclass + to_dict/from_dict 序列化。

8 个固定 Agent 类型定义见 §6.1。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Agent:
    """仿真 Agent 数据模型"""

    id: int
    name: str
    role: str                             # 角色标签
    stance: str                           # "opposing" | "neutral" | "supportive"
    base_stance: str                      # 初始立场（用于复位）
    influence: float                      # 单次发言对世界状态的影响力权重
    activity: float                       # 每轮被激活的概率（0~1）
    emotion: float = 0.0                  # 当前情绪值（-1.0 ~ 1.0）
    trust: float = 0.5                    # 对企业的信任度（0~1）
    active_hours: List[int] = field(default_factory=list)  # 活跃时段（模拟小时）
    profile: str = ""                     # 角色画像（System Prompt）
    memory: List[str] = field(default_factory=list)        # 最近 N 轮记忆摘要

    def reset(self):
        """复位到初始立场和情绪"""
        self.stance = self.base_stance
        self.emotion = 0.0
        self.trust = 0.5
        self.memory.clear()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "stance": self.stance,
            "base_stance": self.base_stance,
            "influence": self.influence,
            "activity": self.activity,
            "emotion": self.emotion,
            "trust": self.trust,
            "active_hours": self.active_hours,
            "profile": self.profile,
            "memory": self.memory,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Agent:
        return cls(**data)


# ============================================================
# 8 个固定 Agent 模板
# ============================================================

AGENT_TEMPLATES: List[dict] = [
    {
        "id": 1,
        "name": "普通消费者 A",
        "role": "情绪型消费者",
        "stance": "opposing",
        "influence": 1.0,
        "activity": 0.8,
        "active_hours": [8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22],
        "profile": "你是一位容易被舆论裹挟的普通消费者，情绪驱动，容易受到社交媒体上负面信息的影响。",
    },
    {
        "id": 2,
        "name": "普通消费者 B",
        "role": "理性消费者",
        "stance": "neutral",
        "influence": 0.8,
        "activity": 0.5,
        "active_hours": [9, 10, 11, 12, 13, 14, 15, 19, 20, 21],
        "profile": "你是一位理性观望的消费者，依赖事实而非情绪，希望看到更多信息再做判断。",
    },
    {
        "id": 3,
        "name": "普通消费者 C",
        "role": "忠诚用户",
        "stance": "supportive",
        "influence": 0.6,
        "activity": 0.3,
        "active_hours": [10, 11, 12, 13, 14, 15, 20, 21],
        "profile": "你是该品牌的忠诚用户，倾向于维护企业形象，愿意给企业解释的机会。",
    },
    {
        "id": 4,
        "name": "媒体人 / KOL",
        "role": "自媒体意见领袖",
        "stance": "opposing",
        "influence": 2.5,
        "activity": 0.9,
        "active_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23],
        "profile": "你是一位追求流量的自媒体人/KOL，初始观望，随热度升高转为对立，倾向放大争议。",
    },
    {
        "id": 5,
        "name": "业内人士",
        "role": "行业专家",
        "stance": "opposing",
        "influence": 1.5,
        "activity": 0.5,
        "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        "profile": "你是一位具有专业背景的业内人士，从专业角度质疑企业的操作规范。",
    },
    {
        "id": 6,
        "name": "监管观察者",
        "role": "监管关注者",
        "stance": "neutral",
        "influence": 2.0,
        "activity": 0.2,
        "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        "profile": "你关注企业合规问题，仅对涉及监管、合规的话题发声，其他话题保持沉默。",
    },
    {
        "id": 7,
        "name": "竞品方",
        "role": "竞争对手",
        "stance": "opposing",
        "influence": 1.8,
        "activity": 0.5,
        "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        "profile": "你来自竞争对手，伺机借势攻击，但会避免过于直接的攻击以免招致反感。",
    },
    {
        "id": 8,
        "name": "企业官方发言人",
        "role": "官方发言人",
        "stance": "supportive",
        "influence": 3.0,
        "activity": 0.0,  # 由策略触发，不随机激活
        "active_hours": list(range(0, 24)),  # 随时可发言
        "profile": "你是企业官方发言人，唯一可控 Agent，按企业声明稿进行回应。维护企业形象是你的首要职责。",
    },
]
