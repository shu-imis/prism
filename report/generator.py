"""报告生成器。

将仿真轮次数据转成结构化评估结果，并给出可解释的策略推荐。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.world_state import WorldState


@dataclass
class StrategyReport:
    """单个策略的评估报告。"""

    strategy_name: str
    strategy_statement: str
    final_heat: float
    final_sentiment: float
    final_support_rate: float
    heat_delta: float = 0.0
    sentiment_delta: float = 0.0
    support_delta: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)
    summary: str = ""
    recommendation: str = ""
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_statement": self.strategy_statement,
            "final_heat": self.final_heat,
            "final_sentiment": self.final_sentiment,
            "final_support_rate": self.final_support_rate,
            "heat_delta": self.heat_delta,
            "sentiment_delta": self.sentiment_delta,
            "support_delta": self.support_delta,
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
        statement: str,
        rounds: list[WorldState],
    ) -> StrategyReport:
        """从仿真轮次数据生成策略报告。"""

        normalized = rounds or [WorldState()]
        first = normalized[0]
        final = normalized[-1]
        heat_delta = final.heat - first.heat
        sentiment_delta = final.sentiment - first.sentiment
        support_delta = final.support_rate - first.support_rate
        key_events = [
            event.description
            for round_state in normalized
            for event in round_state.key_events
        ]
        scores = score_strategy(final, heat_delta, sentiment_delta, support_delta)
        risks = detect_risks(final, heat_delta, sentiment_delta, key_events)

        strategy_report = StrategyReport(
            strategy_name=name,
            strategy_statement=statement,
            final_heat=final.heat,
            final_sentiment=final.sentiment,
            final_support_rate=final.support_rate,
            heat_delta=heat_delta,
            sentiment_delta=sentiment_delta,
            support_delta=support_delta,
            scores=scores,
            key_events=key_events,
            summary=build_strategy_summary(name, final, heat_delta, sentiment_delta, support_delta),
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
    heat_delta: float,
    sentiment_delta: float,
    support_delta: float,
) -> dict[str, float]:
    """生成六维评分，值域 0~100。"""

    return {
        "公信力": _clamp(final.support_rate * 100 + support_delta * 30),
        "传播可控性": _clamp(100 - final.heat + min(0, heat_delta) * -0.2),
        "舆论修复": _clamp((final.sentiment + 1) * 50 + sentiment_delta * 20),
        "稳定性": _clamp(100 - abs(heat_delta) * 0.8 - abs(sentiment_delta) * 20),
        "风险抑制": _clamp(85 - max(0, heat_delta - 10) * 0.7 - len(final.key_events) * 4),
        "执行清晰度": _clamp(65 + support_delta * 40 - max(0, -sentiment_delta) * 15),
    }


def detect_risks(
    final: WorldState,
    heat_delta: float,
    sentiment_delta: float,
    key_events: list[str],
) -> list[str]:
    risks: list[str] = []
    if final.heat >= 75 or heat_delta >= 25:
        risks.append("舆情热度仍处高位，存在二次扩散风险")
    if final.sentiment <= -0.35 or sentiment_delta <= -0.25:
        risks.append("公众情绪明显偏负，需要补充道歉、事实解释或补救承诺")
    if final.support_rate < 0.4:
        risks.append("企业支持率不足，声明可信度需要加强")
    if any("监管" in event for event in key_events):
        risks.append("出现监管相关信号，需准备合规说明")
    return risks


def recommend(scores: dict[str, float], risks: list[str]) -> str:
    average = sum(scores.values()) / max(len(scores), 1)
    if average >= 75 and not risks:
        return "可优先采用"
    if average >= 60:
        return "修改后采用"
    return "不建议直接发布"


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
        return "暂无策略结果，无法形成结论。"
    summary = f"综合热度、情绪和支持率表现，当前推荐策略为：{winner}。" if winner else ""
    hottest = max(strategy_reports, key=lambda item: item.final_heat)
    riskiest = max(strategy_reports, key=lambda item: len(item.risks))
    summary += f"{hottest.strategy_name} 的最终热度最高，需重点控制传播扩散。"
    if riskiest.risks:
        summary += f"{riskiest.strategy_name} 暴露的风险最多，建议发布前补充证据和问答预案。"
    return summary


def build_strategy_summary(
    name: str,
    final: WorldState,
    heat_delta: float,
    sentiment_delta: float,
    support_delta: float,
) -> str:
    return (
        f"{name} 最终热度 {final.heat:.1f}，情绪 {final.sentiment:.2f}，"
        f"支持率 {final.support_rate:.1%}；相较初始热度变化 {heat_delta:+.1f}，"
        f"情绪变化 {sentiment_delta:+.2f}，支持率变化 {support_delta:+.1%}。"
    )


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))
