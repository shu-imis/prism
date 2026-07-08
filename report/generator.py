"""报告生成器

将仿真结果组装为结构化报告数据。
Day 1 版：定义数据模型和接口。
后续迭代：接入 LLM 生成文字解读。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime

from prism.core.world_state import WorldState


@dataclass
class StrategyReport:
    """单个策略的评估报告"""
    strategy_name: str
    strategy_statement: str
    final_heat: float
    final_sentiment: float
    final_support_rate: float

    # 六维评分
    scores: Dict[str, float] = field(default_factory=dict)
    # 关键事件
    key_events: List[str] = field(default_factory=list)
    # LLM 生成的分析
    summary: str = ""
    recommendation: str = ""
    risks: List[str] = field(default_factory=list)


@dataclass
class ProjectReport:
    """完整项目报告"""
    project_name: str
    scenario_background: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    strategy_reports: List[StrategyReport] = field(default_factory=list)
    executive_summary: str = ""
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "scenario_background": self.scenario_background,
            "generated_at": self.generated_at,
            "strategy_reports": [
                {
                    "strategy_name": sr.strategy_name,
                    "strategy_statement": sr.strategy_statement,
                    "final_heat": sr.final_heat,
                    "final_sentiment": sr.final_sentiment,
                    "final_support_rate": sr.final_support_rate,
                    "scores": sr.scores,
                    "key_events": sr.key_events,
                    "summary": sr.summary,
                    "recommendation": sr.recommendation,
                    "risks": sr.risks,
                }
                for sr in self.strategy_reports
            ],
            "executive_summary": self.executive_summary,
            "recommendations": self.recommendations,
        }


class ReportGenerator:
    """报告生成器"""

    def __init__(self, project_name: str = "", scenario_background: str = ""):
        self.report = ProjectReport(
            project_name=project_name,
            scenario_background=scenario_background,
        )

    def add_strategy_result(
        self,
        name: str,
        statement: str,
        rounds: List[WorldState],
    ) -> StrategyReport:
        """从仿真轮次数据生成策略报告"""
        final = rounds[-1] if rounds else WorldState()

        sr = StrategyReport(
            strategy_name=name,
            strategy_statement=statement,
            final_heat=final.heat,
            final_sentiment=final.sentiment,
            final_support_rate=final.support_rate,
            key_events=[e.description for e in final.key_events],
        )
        self.report.strategy_reports.append(sr)
        return sr

    def generate(self) -> ProjectReport:
        """生成最终报告（后续接入 LLM）"""
        return self.report
