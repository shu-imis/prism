"""报告生成器。

将单世界仿真轮次数据转成结构化演化评估结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.world_state import WorldState
from core import clamp

# 六维评估中「风险抵御」的评分键：exporter 引用同一常量，避免硬编码字符串漂移
SCORE_KEY_RESILIENCE = "风险抵御"


@dataclass
class SimulationReport:
    """单世界仿真演化的评估报告。"""

    project_name: str
    scenario_background: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    final_inventory: float = 0.0
    final_cost: float = 0.0
    final_delivery_delay: float = 0.0
    final_service_level: float = 0.0
    final_profit_margin: float = 0.0
    inventory_delta: float = 0.0
    cost_delta: float = 0.0
    delay_delta: float = 0.0
    service_delta: float = 0.0
    margin_delta: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)
    evolution_summary: str = ""
    recommendation: str = ""
    risks: list[str] = field(default_factory=list)
    # LLM 生成的叙述式综合分析（evolution_analysis/risk_analysis/recommendations），
    # 无 Key 或调用失败时为空 dict，仅保留公式化结果
    ai_analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "scenario_background": self.scenario_background,
            "generated_at": self.generated_at,
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
            "evolution_summary": self.evolution_summary,
            "recommendation": self.recommendation,
            "risks": self.risks,
            "ai_analysis": self.ai_analysis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationReport:
        """从持久化的 summary dict 还原报告。"""
        report = cls(
            project_name=data.get("project_name", ""),
            scenario_background=data.get("scenario_background", ""),
            final_inventory=data.get("final_inventory", 0.0),
            final_cost=data.get("final_cost", 0.0),
            final_delivery_delay=data.get("final_delivery_delay", 0.0),
            final_service_level=data.get("final_service_level", 0.0),
            final_profit_margin=data.get("final_profit_margin", 0.0),
            inventory_delta=data.get("inventory_delta", 0.0),
            cost_delta=data.get("cost_delta", 0.0),
            delay_delta=data.get("delay_delta", 0.0),
            service_delta=data.get("service_delta", 0.0),
            margin_delta=data.get("margin_delta", 0.0),
            scores=dict(data.get("scores", {})),
            key_events=list(data.get("key_events", [])),
            evolution_summary=data.get("evolution_summary", ""),
            recommendation=data.get("recommendation", ""),
            risks=list(data.get("risks", [])),
            ai_analysis=dict(data.get("ai_analysis", {}) or {}),
        )
        if data.get("generated_at"):
            report.generated_at = str(data["generated_at"])
        return report


class ReportGenerator:
    """报告生成器。"""

    def __init__(self, project_name: str = "", scenario_background: str = ""):
        self.project_name = project_name
        self.scenario_background = scenario_background
        self._rounds: list[WorldState] = []

    def add_simulation_result(self, rounds: list[WorldState]) -> None:
        """设置单世界仿真的轮次数据。"""
        self._rounds = list(rounds or [])

    def generate(self) -> SimulationReport:
        """生成单世界演化评估报告。"""

        normalized = self._rounds or [WorldState()]
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
        scores = score_evolution(final, inventory_delta, cost_delta, delay_delta, service_delta, margin_delta)
        risks = detect_risks(final, inventory_delta, cost_delta, delay_delta, key_events)

        return SimulationReport(
            project_name=self.project_name,
            scenario_background=self.scenario_background,
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
            evolution_summary=build_evolution_summary(
                normalized, final, inventory_delta, cost_delta, service_delta, margin_delta, key_events
            ),
            recommendation=recommend(scores, risks),
            risks=risks,
        )


def score_evolution(
    final: WorldState,
    inventory_delta: float,
    cost_delta: float,
    delay_delta: float,
    service_delta: float,
    margin_delta: float,
) -> dict[str, float]:
    """生成六维评估，值域 0~100。"""

    return {
        "成本控制": clamp(100 - final.cost_index + min(0, cost_delta) * 0.5),
        "交付稳定性": clamp(100 - final.delivery_delay * 10 - abs(delay_delta) * 15),
        "库存健康度": clamp(final.inventory_level * 0.8 + (10 if inventory_delta > 0 else -5)),
        SCORE_KEY_RESILIENCE: clamp(final.resilience_score),
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
        risks.append("全链亏损预警，需调整行为体配置或种子事件")
    if any("监管" in event for event in key_events):
        risks.append("出现监管介入信号，需准备合规说明")
    if final.service_level < 0.7:
        risks.append("订单满足率过低，存在客户流失风险")
    return risks


def recommend(scores: dict[str, float], risks: list[str]) -> str:
    average = sum(scores.values()) / max(len(scores), 1)
    if average >= 75 and not risks:
        return "演化趋势健康，可参照执行"
    if average >= 60:
        return "整体可控，需针对风险点调整"
    return "演化结果不理想，建议调整行为体配置或种子事件"


def build_evolution_summary(
    rounds: list[WorldState],
    final: WorldState,
    inventory_delta: float,
    cost_delta: float,
    service_delta: float,
    margin_delta: float,
    key_events: list[str],
) -> str:
    first = rounds[0]
    cycles = max(len(rounds) - 1, 0)
    return (
        f"共推演 {cycles} 个周期：库存 {first.inventory_level:.1f} → {final.inventory_level:.1f}"
        f"（{inventory_delta:+.1f}），成本 {first.cost_index:.1f} → {final.cost_index:.1f}"
        f"（{cost_delta:+.1f}），服务水平 {first.service_level:.0%} → {final.service_level:.0%}"
        f"（{service_delta:+.1%}），利润率 {first.profit_margin:+.1%} → {final.profit_margin:+.1%}"
        f"（{margin_delta:+.1%}）；期间触发关键事件 {len(key_events)} 起。"
    )
