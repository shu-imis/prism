"""场景解析器

将用户输入的供应链描述转化为结构化场景数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    """结构化供应链场景"""
    title: str = ""
    industry: str = ""                          # 涉及行业
    background: str = ""                        # 供应链背景描述
    nodes: list[dict] = field(default_factory=list)  # 供应链节点列表
    initial_inventory: float = 75.0             # 初始库存水平 0~100
    baseline_cost: float = 50.0                 # 基线成本指数 0~100
    baseline_service_level: float = 0.85        # 基线服务水平 0~1

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
        return cls(**{
            k: v for k, v in data.items()
            if k in {"title", "industry", "background", "nodes",
                     "initial_inventory", "baseline_cost", "baseline_service_level"}
        })


class ScenarioParser:
    """场景解析器 — 将原始输入转为结构化 Scenario"""

    @staticmethod
    def parse(
        title: str = "",
        industry: str = "",
        background: str = "",
        nodes: list[dict] | None = None,
        initial_inventory: float = 75.0,
        baseline_cost: float = 50.0,
        baseline_service_level: float = 0.85,
    ) -> Scenario:
        """从表单字段构建 Scenario"""
        return Scenario(
            title=title,
            industry=industry,
            background=background,
            nodes=nodes or [],
            initial_inventory=max(0.0, min(100.0, initial_inventory)),
            baseline_cost=max(0.0, min(100.0, baseline_cost)),
            baseline_service_level=max(0.0, min(1.0, baseline_service_level)),
        )
