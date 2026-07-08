"""报告导出

PDF 导出（WeasyPrint）+ 应用内预览（QTextBrowser）。
Day 1 版：定义接口。
后续迭代：实现完整导出。
"""
from __future__ import annotations

from pathlib import Path
from prism.report.generator import ProjectReport


class ReportExporter:
    """报告导出器"""

    @staticmethod
    def export_pdf(report: ProjectReport, output_path: str | Path) -> str:
        """导出 PDF 报告（后续实现）"""
        output_path = Path(output_path)
        # TODO: 使用 WeasyPrint 渲染 HTML → PDF
        # from weasyprint import HTML
        # html = ReportExporter._build_html(report)
        # HTML(string=html).write_pdf(str(output_path))
        return str(output_path)

    @staticmethod
    def export_html(report: ProjectReport) -> str:
        """生成 HTML 报告（用于应用内 QTextBrowser 预览）"""
        return ReportExporter._build_html(report)

    @staticmethod
    def _build_html(report: ProjectReport) -> str:
        """构建报告 HTML（后续完善）"""
        parts = [
            "<html><head><meta charset='utf-8'>",
            "<style>",
            "body { font-family: -apple-system, sans-serif; color: #1B1C23; padding: 40px; }",
            "h1 { color: #5B5FEF; }",
            "h2 { color: #7C3AED; margin-top: 32px; }",
            ".score { display: inline-block; padding: 2px 8px; border-radius: 4px; }",
            ".score-high { background: #10B981; color: #fff; }",
            ".score-mid { background: #F59E0B; color: #fff; }",
            ".score-low { background: #EF4444; color: #fff; }",
            "</style></head><body>",
            f"<h1>{report.project_name} — 推演评估报告</h1>",
        ]

        for sr in report.strategy_reports:
            parts.append(f"<h2>策略：{sr.strategy_name}</h2>")
            parts.append(f"<p>最终热度：{sr.final_heat:.1f} | 情绪：{sr.final_sentiment:.2f} | 支持率：{sr.final_support_rate:.2%}</p>")
            if sr.summary:
                parts.append(f"<p>{sr.summary}</p>")

        parts.append("</body></html>")
        return "\n".join(parts)
