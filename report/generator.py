"""报告生成器。

将仿真轮次数据转成结构化评估结果，并给出可解释的方案推荐。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.world_state import WorldState
from core import clamp


@dataclass
class StrategyReport:
    """单个决策方案的评估报告。"""

    strategy_name: str
    strategy_decision: str
    final_inventory: float
    final_cost: float
    final_delivery_delay: float
    final_service_level: float = 0.0
    final_profit_margin: float = 0.0
    inventory_delta: float = 0.0
    cost_delta: float = 0.0
    delay_delta: float = 0.0
    service_delta: float = 0.0
    margin_delta: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)
    summary: str = ""
    recommendation: str = ""
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_decision": self.strategy_decision,
            "final_inventory": self.final_inventory,
            "final_cost": self.final_cost,
            "final_delivery_delay": self.final_delivery_delay,
            "final_service_level": self.final_service_level,
            "final_profit_margin": self.final_profit_margin,
            "inventory_delta": self.inventory_delta,
            "cost_delta": self.cost_delta,
            "delay_delta": self.delay_delta,
            "service_delta": self.service_delta,
            "margin_delta": self.margin_delta,
            "scores": self.scores,
            "key_events": self.key_events,
            "summary": self.summary,
            "recommendation": self.recommendation,
            "risks": self.risks,
        }


@dataclass
class ProjectReport:
    """完整项目报告。"""

    project_name: str
    scenario_background: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    strategy_reports: list[StrategyReport] = field(default_factory=list)
    executive_summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    winner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "scenario_background": self.scenario_background,
            "generated_at": self.generated_at,
            "strategy_reports": [report.to_dict() for report in self.strategy_reports],
            "executive_summary": self.executive_summary,
            "recommendations": self.recommendations,
            "winner": self.winner,
        }


class ReportGenerator:
    """报告生成器。"""

    def __init__(self, project_name: str = "", scenario_background: str = ""):
        self.report = ProjectReport(
            project_name=project_name,
            scenario_background=scenario_background,
        )

    def add_strategy_result(
        self,
        name: str,
        decision: str,
        rounds: list[WorldState],
    ) -> StrategyReport:
        """从仿真轮次数据生成方案报告。"""

        normalized = rounds or [WorldState()]
        first = normalized[0]
        final = normalized[-1]
        inventory_delta = final.inventory_level - first.inventory_level
        cost_delta = final.cost_index - first.cost_index
        delay_delta = final.delivery_delay - first.delivery_delay
        service_delta = final.service_level - first.service_level
        margin_delta = final.profit_margin - first.profit_margin
        key_events = [
            event.description
            for round_state in normalized
            for event in round_state.key_events
        ]
        scores = score_strategy(final, inventory_delta, cost_delta, delay_delta, service_delta, margin_delta)
        risks = detect_risks(final, inventory_delta, cost_delta, delay_delta, key_events)

        strategy_report = StrategyReport(
            strategy_name=name,
            strategy_decision=decision,
            final_inventory=final.inventory_level,
            final_cost=final.cost_index,
            final_delivery_delay=final.delivery_delay,
            final_service_level=final.service_level,
            final_profit_margin=final.profit_margin,
            inventory_delta=inventory_delta,
            cost_delta=cost_delta,
            delay_delta=delay_delta,
            service_delta=service_delta,
            margin_delta=margin_delta,
            scores=scores,
            key_events=key_events,
            summary=build_strategy_summary(name, final, inventory_delta, cost_delta, delay_delta, service_delta, margin_delta),
            recommendation=recommend(scores, risks),
            risks=risks,
        )
        self.report.strategy_reports.append(strategy_report)
        return strategy_report

    def generate(self) -> ProjectReport:
        """生成最终报告。"""

        self.report.winner = select_winner(self.report.strategy_reports)
        self.report.executive_summary = build_executive_summary(
            self.report.strategy_reports,
            self.report.winner,
        )
        self.report.recommendations = [
            f"{item.strategy_name}: {item.recommendation}"
            for item in self.report.strategy_reports
        ]
        return self.report


def score_strategy(
    final: WorldState,
    inventory_delta: float,
    cost_delta: float,
    delay_delta: float,
    service_delta: float,
    margin_delta: float,
) -> dict[str, float]:
    """生成六维评分，值域 0~100。"""

    return {
        "成本控制": clamp(100 - final.cost_index + min(0, cost_delta) * 0.5),
        "交付稳定性": clamp(100 - final.delivery_delay * 10 - abs(delay_delta) * 15),
        "库存健康度": clamp(final.inventory_level * 0.8 + (10 if inventory_delta > 0 else -5)),
        "风险抵御": clamp(final.resilience_score),
        "协同效率": clamp(final.service_level * 100 + service_delta * 30),
        "可执行性": clamp(65 + margin_delta * 40),
    }


def detect_risks(
    final: WorldState,
    inventory_delta: float,
    cost_delta: float,
    delay_delta: float,
    key_events: list[str],
) -> list[str]:
    risks: list[str] = []
    if final.inventory_level < 30 or inventory_delta <= -15:
        risks.append("库存水平过低，存在断供风险")
    if final.cost_index >= 75 or cost_delta >= 15:
        risks.append("成本指数超标，利润率承压")
    if final.delivery_delay >= 3 or delay_delta >= 1.5:
        risks.append("交付延迟严重，客户满意度下降")
    if final.profit_margin < 0:
        risks.append("全链亏损预警，需紧急调整方案")
    if any("监管" in event for event in key_events):
        risks.append("出现监管介入信号，需准备合规说明")
    if final.service_level < 0.7:
        risks.append("订单满足率过低，存在客户流失风险")
    return risks


def recommend(scores: dict[str, float], risks: list[str]) -> str:
    average = sum(scores.values()) / max(len(scores), 1)
    if average >= 75 and not risks:
        return "可优先采用"
    if average >= 60:
        return "修改后采用"
    return "不建议直接执行"


def select_winner(strategy_reports: list[StrategyReport]) -> str | None:
    if not strategy_reports:
        return None
    ranked = sorted(
        strategy_reports,
        key=lambda item: sum(item.scores.values()) / max(len(item.scores), 1),
        reverse=True,
    )
    return ranked[0].strategy_name


def build_executive_summary(strategy_reports: list[StrategyReport], winner: str | None) -> str:
    if not strategy_reports:
        return "暂无可评估的方案结果。"
    summary = f"综合库存、成本、交付时效和服务水平表现，当前推荐方案为：{winner}。" if winner else ""
    worst_cost = max(strategy_reports, key=lambda item: item.final_cost)
    riskiest = max(strategy_reports, key=lambda item: len(item.risks))
    summary += f"{worst_cost.strategy_name} 的最终成本最高，需重点控制成本结构。"
    if riskiest.risks:
        summary += f"{riskiest.strategy_name} 暴露的风险最多，建议修订决策参数和应急预案。"
    return summary


def build_strategy_summary(
    name: str,
    final: WorldState,
    inventory_delta: float,
    cost_delta: float,
    delay_delta: float,
    service_delta: float,
    margin_delta: float,
) -> str:
    return (
        f"{name} 最终库存 {final.inventory_level:.1f}，成本 {final.cost_index:.1f}，"
        f"交付延迟 {final.delivery_delay:.1f} 周期，服务水平 {final.service_level:.0%}，"
        f"利润率 {final.profit_margin:+.1%}；"
        f"库存变化 {inventory_delta:+.1f}，成本变化 {cost_delta:+.1f}，"
        f"延迟变化 {delay_delta:+.1f}，服务变化 {service_delta:+.2f}，"
        f"利润变化 {margin_delta:+.1%}。"
    )

