from __future__ import annotations

import unittest

from core.world_state import AgentSnapshot, KeyEvent, WorldState
from llm.client import LLMClient, LLMProvider, ProviderSettings
import llm.analysis as llm_analysis
from report.exporter import ReportExporter
from report.generator import ReportGenerator, SimulationReport
from tests.helpers import make_json_client


class ReportingTests(unittest.TestCase):
    def test_report_generation_and_exports(self) -> None:
        """验证单世界报告生成和 Markdown 导出。"""
        rounds = [
            WorldState(round=0, simulated_hour=0, inventory_level=80, cost_index=50, delivery_delay=0.5),
            WorldState(
                round=1,
                simulated_hour=1,
                inventory_level=70,
                cost_index=55,
                delivery_delay=1.0,
                service_level=0.82,
                profit_margin=0.10,
                resilience_score=60.0,
                key_events=[
                    KeyEvent(
                        round=1,
                        simulated_hour=1,
                        event_type="raw_material_shortage",
                        description="原材料断供",
                    )
                ],
                agent_states={
                    2: AgentSnapshot(
                        agent_id=2,
                        spoke=True,
                        decision_summary="减产保价",
                        action_type="adjust_capacity",
                        reaction_to="原材料供应商",
                    ),
                },
            ),
        ]
        generator = ReportGenerator(
            project_name="Prism",
            scenario_background="电子产品供应链推演",
        )
        generator.add_simulation_result(rounds)
        report = generator.generate()
        markdown = ReportExporter.to_markdown(report, rounds)

        self.assertEqual(report.final_inventory, 70.0)
        self.assertEqual(report.inventory_delta, -10.0)
        self.assertIn("原材料断供", report.key_events)
        self.assertIn("演化概述", markdown)
        self.assertIn("供应链演化仿真报告", markdown)
        # 逐轮数据表与演化时间线（含行动类型与回应关系）进入导出
        self.assertIn("## 指标演化数据", markdown)
        self.assertIn("| 1 | 70.0 |", markdown)
        self.assertIn("## 演化时间线", markdown)
        self.assertIn("⚡ 原材料断供", markdown)
        self.assertIn("制造商【adjust_capacity】 回应@原材料供应商", markdown)

    def test_export_normalizes_speech_punctuation(self) -> None:
        """导出的 Markdown 时间线与 UI 一样经过标点规范化（句末补句号）。"""
        generator = ReportGenerator("demo", "背景")
        rounds = [
            WorldState(
                round=1,
                agent_states={
                    2: AgentSnapshot(
                        agent_id=2,
                        pressure=0.1,
                        decision_stance="cooperative",
                        spoke=True,
                        speech="促销订单增长,需要补货",
                        action_type="adjust_supply",
                        reaction_to="none",
                    )
                },
            )
        ]
        generator.add_simulation_result(rounds)
        report = generator.generate()

        markdown = ReportExporter.to_markdown(report, rounds)

        self.assertIn("促销订单增长，需要补货。", markdown)

    def test_analyze_evolution_and_report_round_trip(self) -> None:
        """演化分析：LLM 叙述写入 report.ai_analysis，序列化往返保留；失败时抛异常供降级。"""
        generator = ReportGenerator("demo", "背景")
        generator.add_simulation_result([
            WorldState(round=0, inventory_level=70, cost_index=50, service_level=0.85),
            WorldState(round=1, inventory_level=55, cost_index=62, service_level=0.7),
        ])
        report = generator.generate()
        self.assertEqual(report.ai_analysis, {})

        payload = (
            '{"evolution_analysis": "库存持续下滑，主因是供应商收紧供应。", '
            '"risk_analysis": "断供风险沿上游传导。", '
            '"recommendations": ["提高安全库存", "引入备选供应商"], "extra": 1}'
        )
        analysis = llm_analysis.analyze_evolution(
            make_json_client(payload), report, []
        )
        report.ai_analysis = analysis

        self.assertIn("库存持续下滑", analysis["evolution_analysis"])
        self.assertEqual(len(analysis["recommendations"]), 2)

        restored = SimulationReport.from_dict(report.to_dict())
        self.assertEqual(restored.ai_analysis["risk_analysis"], "断供风险沿上游传导。")

        markdown = ReportExporter.to_markdown(report)
        self.assertIn("## AI 综合分析", markdown)
        self.assertIn("提高安全库存", markdown)

        def failing_transport(provider, messages, options):
            raise RuntimeError("boom")

        failing_client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "m", "key")],
            max_retries=0,
            transport=failing_transport,
        )
        with self.assertRaises(Exception):
            llm_analysis.analyze_evolution(failing_client, report, [])


if __name__ == "__main__":
    unittest.main()
