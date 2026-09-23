"""场景解析器

将用户输入的供应链描述转化为结构化场景数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from core import clamp

# 场景基线默认值（表单兜底 / AI 校验兜底 / DB 恢复兜底共用）
DEFAULT_INITIAL_INVENTORY = 75.0
DEFAULT_BASELINE_COST = 50.0
DEFAULT_BASELINE_SERVICE_LEVEL = 0.85


@dataclass
class Scenario:
    """结构化供应链场景"""
    title: str = ""
    industry: str = ""                          # 涉及行业
    background: str = ""                        # 供应链背景描述
    nodes: list[dict] = field(default_factory=list)  # 供应链节点列表
    initial_inventory: float = DEFAULT_INITIAL_INVENTORY   # 初始库存水平 0~100
    baseline_cost: float = DEFAULT_BASELINE_COST           # 基线成本指数 0~100
    baseline_service_level: float = DEFAULT_BASELINE_SERVICE_LEVEL  # 基线服务水平 0~1

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "industry": self.industry,
            "background": self.background,
            "nodes": self.nodes,
            "initial_inventory": self.initial_inventory,
            "baseline_cost": self.baseline_cost,
            "baseline_service_level": self.baseline_service_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Scenario:
        # 复用 parse 的数值钳制：DB 恢复路径同样受 clamp 保护
        return ScenarioParser.parse(
            title=data.get("title", ""),
            industry=data.get("industry", ""),
            background=data.get("background", ""),
            nodes=data.get("nodes", []),
            initial_inventory=data.get("initial_inventory", DEFAULT_INITIAL_INVENTORY),
            baseline_cost=data.get("baseline_cost", DEFAULT_BASELINE_COST),
            baseline_service_level=data.get("baseline_service_level", DEFAULT_BASELINE_SERVICE_LEVEL),
        )


class ScenarioParser:
    """提供 parse / from_dict 两个构建 Scenario 的入口。"""

    @staticmethod
    def parse(
        title: str = "",
        industry: str = "",
        background: str = "",
        nodes: list[dict] | None = None,
        initial_inventory: float = DEFAULT_INITIAL_INVENTORY,
        baseline_cost: float = DEFAULT_BASELINE_COST,
        baseline_service_level: float = DEFAULT_BASELINE_SERVICE_LEVEL,
    ) -> Scenario:
        """从表单字段构建 Scenario"""
        return Scenario(
            title=title,
            industry=industry,
            background=background,
            nodes=nodes or [],
            initial_inventory=clamp(initial_inventory, 0.0, 100.0),
            baseline_cost=clamp(baseline_cost, 0.0, 100.0),
            baseline_service_level=clamp(baseline_service_level, 0.0, 1.0),
        )
