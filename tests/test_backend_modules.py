from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.world_state import KeyEvent, WorldState
from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRoundRepository,
    StrategyRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.exporter import ReportExporter
from report.generator import ReportGenerator


class BackendModuleTests(unittest.TestCase):
    def test_database_repositories_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()

            project_repo = ProjectRepository(db)
            strategy_repo = StrategyRepository(db)
            round_repo = SimulationRoundRepository(db)
            report_repo = ReportRepository(db)

            project = project_repo.create("Demo", {"industry": "retail"})
            strategy = strategy_repo.create(
                project.id,
                name="快速道歉",
                statement="我们已经启动调查并同步整改。",
                release_hour=4,
            )

            saved_round = round_repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                round_index=1,
                simulated_hour=4,
                heat=62.5,
                sentiment=-0.2,
                support_rate=0.48,
                state={"key_events": ["媒体跟进报道"]},
                agent_messages=[
                    {
                        "agent_name": "媒体人 / KOL",
                        "stance": "opposing",
                        "content": "还需要更多证据。",
                    }
                ],
            )
            updated_round = round_repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                round_index=1,
                simulated_hour=4,
                heat=58.0,
                sentiment=-0.1,
                support_rate=0.51,
                state={"key_events": ["情绪回落"]},
            )

            self.assertEqual(saved_round.id, updated_round.id)
            self.assertEqual(round_repo.list_by_strategy(strategy.id)[0].heat, 58.0)

            report_id = report_repo.save(
                project_id=project.id,
                title="Demo 报告",
                markdown="# Demo",
                html="<h1>Demo</h1>",
                summary={"winner": "快速道歉"},
            )
            self.assertEqual(report_repo.list_by_project(project.id)[0].id, report_id)
            db.close()

    def test_llm_json_fallback(self) -> None:
        calls: list[str] = []

        def fake_transport(provider, messages, options):
            calls.append(provider.provider.value)
            if provider.provider == LLMProvider.OPENAI:
                raise RuntimeError("temporary outage")
            return 'analysis\n```json\n{"score": 88, "ok": true,}\n```'

        client = LLMClient(
            providers=[
                ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key"),
                ProviderSettings(LLMProvider.ANTHROPIC, "claude", "key"),
            ],
            max_retries=0,
            transport=fake_transport,
        )

        result = client.chat_json("只返回 JSON", "score")
        self.assertEqual(result["score"], 88)
        self.assertEqual(calls, ["openai", "anthropic"])

    def test_report_generation_and_exports(self) -> None:
        generator = ReportGenerator(
            project_name="Prism",
            scenario_background="品牌声明前的舆情预演",
        )
        generator.add_strategy_result(
            "策略 A",
            "先道歉再解释。",
            [
                WorldState(round=0, simulated_hour=0, heat=50, sentiment=-0.4, support_rate=0.35),
                WorldState(
                    round=1,
                    simulated_hour=4,
                    heat=45,
                    sentiment=-0.1,
                    support_rate=0.52,
                    key_events=[
                        KeyEvent(
                            round=1,
                            simulated_hour=4,
                            event_type="media_follow",
                            description="媒体跟进报道",
                        )
                    ],
                ),
            ],
        )
        report = generator.generate()
        markdown = ReportExporter.to_markdown(report)
        html = ReportExporter.export_html(report)

        self.assertEqual(report.winner, "策略 A")
        self.assertIn("策略 A", markdown)
        self.assertIn("<h1>", html)


if __name__ == "__main__":
    unittest.main()
