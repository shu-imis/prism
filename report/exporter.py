"""报告导出。

提供 Markdown 格式的报告导出，结构与结果页一致：
概述、背景、指标变化、指标演化数据、演化时间线、六维评估、风险与建议、
AI 综合分析（如有）。
"""
from __future__ import annotations

from pathlib import Path

from core.text_utils import normalize_speech
from core.world_state import WorldState
from report.generator import SimulationReport
from report.timeline import AGENT_NAMES, build_timeline_entries, format_rounds_span


class ReportExporter:
    """报告导出器。"""

    @staticmethod
    def export_markdown(report: SimulationReport, output_path: str | Path, rounds: list[WorldState] | None = None) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ReportExporter.to_markdown(report, rounds), encoding="utf-8")
        return str(output_path)

    @staticmethod
    def to_markdown(report: SimulationReport, rounds: list[WorldState] | None = None) -> str:
        resilience = report.scores.get("风险抵御", 0)
        lines = [
            f"# {report.project_name} - 供应链演化仿真报告",
            "",
            "## 演化概述",
            report.evolution_summary or "暂无摘要。",
            "",
            "## 供应链背景",
            report.scenario_background or "未填写。",
            "",
            "## 指标变化",
            "| 指标 | 末态 | 首末变化 |",
            "| --- | ---: | ---: |",
            f"| 库存水平 | {report.final_inventory:.1f} | {report.inventory_delta:+.1f} |",
            f"| 成本指数 | {report.final_cost:.1f} | {report.cost_delta:+.1f} |",
            f"| 交付延迟 | {report.final_delivery_delay:.1f} 周期 | {report.delay_delta:+.1f} |",
            f"| 服务水平 | {report.final_service_level:.0%} | {report.service_delta:+.2f} |",
            f"| 利润率 | {report.final_profit_margin:+.1%} | {report.margin_delta:+.1%} |",
            f"| 风险抵御 | {resilience:.1f} | — |",
        ]

        if rounds:
            lines.extend(["", "## 指标演化数据", ""])
            lines.extend(ReportExporter._metrics_table(rounds))
            lines.extend(["", "## 演化时间线", ""])
            lines.extend(ReportExporter._timeline_lines(rounds))

        lines.extend(["", "## 六维评估"])
        lines.extend(f"- {key}：{value:.1f}" for key, value in report.scores.items())
        lines.append(f"- 综合建议：{report.recommendation}")
        lines.extend(["", "## 风险与建议"])
        if report.risks:
            lines.extend(f"- {risk}" for risk in report.risks)
        else:
            lines.append("- 暂无明显高风险信号")

        ai = report.ai_analysis or {}
        if ai.get("evolution_analysis"):
            lines.extend(["", "## AI 综合分析", "", ai["evolution_analysis"]])
            if ai.get("risk_analysis"):
                lines.extend(["", "### 风险归因", "", ai["risk_analysis"]])
            recommendations = ai.get("recommendations", [])
            if recommendations:
                lines.extend(["", "### AI 建议", ""])
                lines.extend(f"- {item}" for item in recommendations)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _metrics_table(rounds: list[WorldState]) -> list[str]:
        """按周期的指标快照 Markdown 表格。"""
        lines = [
            "| 周期 | 库存 | 成本 | 交付延迟 | 服务水平 | 利润率 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for state in rounds:
            lines.append(
                f"| {state.round} | {state.inventory_level:.1f} | {state.cost_index:.1f} | "
                f"{state.delivery_delay:.1f} | {state.service_level:.0%} | {state.profit_margin:+.1%} |"
            )
        return lines

    @staticmethod
    def _timeline_lines(rounds: list[WorldState]) -> list[str]:
        """演化时间线 Markdown 条目：事件与行为体行动片段按周期交织。"""
        entries = build_timeline_entries(rounds)
        if not entries:
            return ["- 本轮演化无关键事件与行为体行动"]
        lines = []
        for entry in entries:
            if entry["kind"] == "event":
                lines.append(f"- 周期 {entry['round']}：⚡ {entry['description']}")
                continue
            name = AGENT_NAMES.get(entry["agent_id"], f"行为体{entry['agent_id']}")
            span = format_rounds_span(entry["start"], entry["end"])
            action = f"【{entry['action_type']}】" if entry["action_type"] else ""
            reaction = ""
            if entry["reaction_to"] and entry["reaction_to"] != "none":
                reaction = f" 回应@{entry['reaction_to']}"
            duration = ""
            if entry["end"] > entry["start"]:
                duration = f"（持续 {entry['end'] - entry['start'] + 1} 轮）"
            lines.append(f"- {span}：{name}{action}{reaction}：{normalize_speech(entry['summary'])}{duration}")
        return lines
