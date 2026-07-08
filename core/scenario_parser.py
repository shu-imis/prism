"""场景解析器

将用户输入的事件描述转化为结构化场景数据。
Day 1 版：定义数据模型，后续接入 LLM 解析。
参考 MiroFish SimulationConfigGenerator 的分步生成策略。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Scenario:
    """结构化危机场景"""
    title: str = ""
    industry: str = ""                    # 涉及行业
    background: str = ""                  # 事件背景描述
    company_statement: str = ""           # 企业现有声明稿
    initial_heat: float = 0.0            # 初始热度（0~100）
    baseline_sentiment: float = 0.0      # 公众情绪基线（-1.0 ~ 1.0）
    key_entities: List[str] = field(default_factory=list)  # 关键实体

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "industry": self.industry,
            "background": self.background,
            "company_statement": self.company_statement,
            "initial_heat": self.initial_heat,
            "baseline_sentiment": self.baseline_sentiment,
            "key_entities": self.key_entities,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Scenario:
        return cls(**data)


class ScenarioParser:
    """场景解析器 — 将原始输入转为结构化 Scenario"""

    @staticmethod
    def parse(
        title: str = "",
        industry: str = "",
        background: str = "",
        company_statement: str = "",
        initial_heat: float = 30.0,
        baseline_sentiment: float = -0.2,
    ) -> Scenario:
        """从表单字段构建 Scenario"""
        return Scenario(
            title=title,
            industry=industry,
            background=background,
            company_statement=company_statement,
            initial_heat=max(0.0, min(100.0, initial_heat)),
            baseline_sentiment=max(-1.0, min(1.0, baseline_sentiment)),
        )
