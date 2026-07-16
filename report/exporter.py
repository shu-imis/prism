"""报告导出。

提供 Markdown 和 HTML 格式的报告导出。
"""
from __future__ import annotations

from pathlib import Path

from report.generator import ProjectReport


class ReportExporter:
    """报告导出器。"""

    @staticmethod
    def export_markdown(report: ProjectReport, output_path: str | Path) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ReportExporter.to_markdown(report), encoding="utf-8")
        return str(output_path)

    @staticmethod
    def export_html(report: ProjectReport) -> str:
        return ReportExporter._render_html(report)

    @staticmethod
    def to_markdown(report: ProjectReport) -> str:
        lines = [
            f"# {report.project_name} - 供应链决策推演报告",
            "",
            "## 执行摘要",
            report.executive_summary or "暂无摘要。",
            "",
            "## 供应链背景",
            report.scenario_background or "未填写。",
            "",
            "## 方案对比",
            "| 方案 | 库存 | 成本 | 交付延迟 | 服务水平 | 利润率 | 韧性 | 建议 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for item in report.strategy_reports:
            resilience = item.scores.get("风险抵御", 0)
            lines.append(
                f"| {item.strategy_name} | {item.final_inventory:.1f} | {item.final_cost:.1f} | "
                f"{item.final_delivery_delay:.1f} | {item.final_service_level:.0%} | "
                f"{item.final_profit_margin:+.1%} | {resilience:.1f} | {item.recommendation} |"
            )

        lines.extend(["", "## 分方案分析"])
        for item in report.strategy_reports:
            lines.extend(
                [
                    "",
                    f"### {item.strategy_name}",
                    f"- 决策内容：{item.strategy_decision or '未填写'}",
                    f"- 库存变化：{item.inventory_delta:+.1f}",
                    f"- 成本变化：{item.cost_delta:+.1f}",
                    f"- 交付延迟变化：{item.delay_delta:+.1f} 周期",
                    f"- 服务水平变化：{item.service_delta:+.2f}",
                    f"- 利润率变化：{item.margin_delta:+.1%}",
                    "- 六维评分：" + "；".join(f"{key} {value:.1f}" for key, value in item.scores.items()),
                    "- 关键风险：" + ("；".join(item.risks) if item.risks else "暂无明显高风险信号"),
                    "- 关键事件：" + ("；".join(item.key_events) if item.key_events else "无"),
                ]
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_html(report: ProjectReport) -> str:
        parts: list[str] = [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'>",
            "<style>",
            "body{font-family:-apple-system,BlinkMacSystemFont,'Noto Sans SC',sans-serif;",
            "color:#1D1D1F;margin:40px;line-height:1.65;}",
            "h1{font-size:24px;margin-top:24px;}",
            "h2{font-size:16px;margin-top:20px;border-bottom:1px solid #D2D2D7;padding-bottom:4px;}",
            "table{border-collapse:collapse;width:100%;margin:12px 0;}",
            "th,td{border:1px solid #E8E8E5;padding:6px 10px;text-align:left;}",
            "th{background:#F5F5F0;font-weight:600;}",
            "pre{white-space:pre-wrap;background:#F5F5F7;padding:8px;border-radius:6px;}",
            "</style></head><body>",
        ]

        markdown = ReportExporter.to_markdown(report)
        for line in markdown.splitlines():
            if line.startswith("# "):
                parts.append(f"<h1>{_esc(line[2:])}</h1>")
            elif line.startswith("## "):
                parts.append(f"<h2>{_esc(line[3:])}</h2>")
            elif line.startswith("### "):
                parts.append(f"<h3>{_esc(line[4:])}</h3>")
            elif line.startswith("|"):
                parts.append(f"<pre>{_esc(line)}</pre>")
            elif line.startswith("- "):
                parts.append(f"<p>{_esc(line)}</p>")
            elif line.strip():
                parts.append(f"<p>{_esc(line)}</p>")

        parts.append("</body></html>")
        return "\n".join(parts)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
