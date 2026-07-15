"""报告导出。

提供应用内 HTML 预览、Markdown 导出，以及 WeasyPrint 可用时的 PDF 导出。
"""
from __future__ import annotations

import html
from pathlib import Path

from report.generator import ProjectReport


class ReportExporter:
    """报告导出器。"""

    @staticmethod
    def export_pdf(report: ProjectReport, output_path: str | Path) -> str:
        """导出 PDF；若 WeasyPrint 环境不可用，则降级写入 HTML。"""

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = ReportExporter.export_html(report)
        try:
            from weasyprint import HTML
        except Exception:
            fallback = output_path.with_suffix(".html")
            fallback.write_text(html_content, encoding="utf-8")
            return str(fallback)

        HTML(string=html_content).write_pdf(str(output_path))
        return str(output_path)

    @staticmethod
    def export_markdown(report: ProjectReport, output_path: str | Path) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ReportExporter.to_markdown(report), encoding="utf-8")
        return str(output_path)

    @staticmethod
    def export_html(report: ProjectReport) -> str:
        return ReportExporter._build_html(report)

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
            lines.append(
                "| {name} | {inv:.1f} | {cost:.1f} | {delay:.1f} | {svc:.0%} | {margin:+.1%} | {resilience:.1f} | {rec} |".format(
                    name=item.strategy_name,
                    inv=item.final_inventory,
                    cost=item.final_cost,
                    delay=item.final_delivery_delay,
                    svc=item.final_service_level,
                    margin=item.final_profit_margin,
                    resilience=item.scores.get("风险抵御", 0),
                    rec=item.recommendation,
                )
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
    def _build_html(report: ProjectReport) -> str:
        markdown = ReportExporter.to_markdown(report)
        body: list[str] = []
        for line in markdown.splitlines():
            safe = html.escape(line)
            if line.startswith("# "):
                body.append(f"<h1>{html.escape(line[2:])}</h1>")
            elif line.startswith("## "):
                body.append(f"<h2>{html.escape(line[3:])}</h2>")
            elif line.startswith("### "):
                body.append(f"<h3>{html.escape(line[4:])}</h3>")
            elif line.startswith("- "):
                body.append(f"<p>{safe}</p>")
            elif line.startswith("|"):
                body.append(f"<pre>{safe}</pre>")
            elif line.strip():
                body.append(f"<p>{safe}</p>")

        return "\n".join(
            [
                "<!doctype html>",
                "<html><head><meta charset='utf-8'>",
                "<style>",
                "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;",
                "color:#1D1D1F;margin:40px;line-height:1.65;}",
                "h1{font-size:28px} h2{margin-top:28px;border-bottom:1px solid #D2D2D7;padding-bottom:6px}",
                "pre{white-space:pre-wrap;background:#F5F5F7;padding:8px;border-radius:6px}",
                "</style></head><body>",
                *body,
                "</body></html>",
            ]
        )
