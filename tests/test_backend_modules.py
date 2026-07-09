from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.agent_factory import AgentFactory
from core.document_importer import chunk_text, import_documents, render_imported_documents
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from core.world_state import KeyEvent, WorldState
from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRoundRepository,
    StrategyRepository,
    CheckpointRepository,
    KnowledgeRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
from report.exporter import ReportExporter
from report.generator import ReportGenerator


class BackendModuleTests(unittest.TestCase):
    def _fake_llm_client(self, official_calls: list[int] | None = None) -> LLMClient:
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            if "企业官方发言人" in system and "企业声明稿" in system:
                if official_calls is not None:
                    official_calls.append(1)
                return '{"speech": "我们诚恳致歉并公开整改进展。", "tone": "transparent"}'
            if "监管" in system or "监管关注者" in system:
                return (
                    '{"emotion_change": -0.05, "trust_change": -0.08, '
                    '"speech": "这个事件需要关注合规和监管调查进展。", '
                    '"spread_intent": 0.7, "stance_shift": "toward_opposing"}'
                )
            if "媒体" in system or "KOL" in system:
                return (
                    '{"emotion_change": -0.1, "trust_change": -0.05, '
                    '"speech": "我会进一步调查这件事背后的真相。", '
                    '"spread_intent": 0.9, "stance_shift": "toward_opposing"}'
                )
            return (
                '{"emotion_change": 0.04, "trust_change": 0.06, '
                '"speech": "透明回应让我愿意继续观察。", '
                '"spread_intent": 0.45, "stance_shift": "toward_supportive"}'
            )

        return LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )

    def _always_active_agents(self):
        agents = AgentFactory.create_all()
        for agent in agents:
            if agent.id != 8:
                agent.activity = 1.0
                agent.active_hours = list(range(24))
        return agents

    def test_database_repositories_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()

            project_repo = ProjectRepository(db)
            strategy_repo = StrategyRepository(db)
            round_repo = SimulationRoundRepository(db)
            report_repo = ReportRepository(db)

            project = project_repo.create("Demo", {"industry": "retail"})
            project = project_repo.update_scenario(
                project.id,
                {"title": "更新后的事件", "industry": "food", "initial_heat": 50},
                name="更新后的事件",
            )
            self.assertEqual(project.name, "更新后的事件")
            self.assertEqual(project.scenario["industry"], "food")
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

    def test_strategy_replace_for_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "retail"})
            repo = StrategyRepository(db)
            repo.create(project.id, "旧策略", "旧声明", 4)

            saved = repo.replace_for_project(
                project.id,
                [
                    {"name": "策略 A", "statement": "先道歉。", "release_hour": 4},
                    {"name": "策略 B", "statement": "先核查。", "release_hour": 8},
                    {"name": "策略 C", "statement": "同步补偿。", "release_hour": 12},
                ],
            )

            self.assertEqual(len(saved), 3)
            self.assertEqual([item.name for item in repo.list_by_project(project.id)], ["策略 A", "策略 B", "策略 C"])
            db.close()

    def test_document_importer_reads_text_documents_with_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "background.md"
            path.write_text("# 事件背景\n\n消费者发布了门店卫生视频。", encoding="utf-8")

            imported = import_documents([path], max_total_chars=20)
            rendered = render_imported_documents(imported)
            chunks = chunk_text(imported[0].text, max_chars=8, overlap=2)

            self.assertEqual(len(imported), 1)
            self.assertIn("background.md", rendered)
            self.assertLessEqual(len(imported[0].text), 20)
            self.assertGreaterEqual(len(chunks), 2)

    def test_knowledge_repository_replace_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "retail"})
            repo = KnowledgeRepository(db)

            repo.replace_for_project(
                project.id,
                [
                    {"source": "a.md", "chunk_index": 0, "content": "门店卫生 视频 消费者 投诉"},
                    {"source": "b.md", "chunk_index": 0, "content": "供应链 价格 活动"},
                ],
            )
            hits = repo.search(project.id, "消费者关注门店卫生", limit=1)

            self.assertEqual(len(repo.list_by_project(project.id)), 2)
            self.assertEqual(hits[0].source, "a.md")
            db.close()

    def test_checkpoint_repository_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "retail"})
            strategy = StrategyRepository(db).create(project.id, "快速道歉", "声明", 4)
            repo = CheckpointRepository(db)

            checkpoint_id = repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                last_round=2,
                engine_state={"strategy_index": 0, "last_round": 2},
            )
            latest = repo.latest_for_project(project.id)

            self.assertIsNotNone(latest)
            self.assertEqual(latest.id, checkpoint_id)
            self.assertEqual(latest.engine_state["last_round"], 2)
            self.assertEqual(len(repo.list_unfinished()), 1)
            repo.delete_for_project(project.id)
            self.assertIsNone(repo.latest_for_project(project.id))
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

    def test_llm_custom_compatible_base_url(self) -> None:
        observed = []

        def fake_transport(provider, messages, options):
            observed.append(provider)
            return '{"ok": true}'

        client = LLMClient(
            providers=[
                ProviderSettings(
                    LLMProvider.OPENAI,
                    "deepseek-chat",
                    "key",
                    "https://api.deepseek.com",
                )
            ],
            max_retries=0,
            transport=fake_transport,
        )

        result = client.chat_json("只返回 JSON", "ping")
        self.assertTrue(result["ok"])
        self.assertEqual(observed[0].provider, LLMProvider.OPENAI)
        self.assertEqual(observed[0].model, "deepseek-chat")
        self.assertEqual(observed[0].base_url, "https://api.deepseek.com")

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

    def test_simulation_engine_runs_llm_rounds_and_events(self) -> None:
        scenario = ScenarioParser.parse(
            title="Demo 危机",
            industry="餐饮",
            background="门店卫生争议正在扩散。",
            company_statement="正在核查。",
            initial_heat=65,
            baseline_sentiment=-0.35,
        )
        engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=7)
        round_payloads = []
        engine.set_round_callback(lambda si, strategy, state, messages: round_payloads.append((state, messages)))
        engine.configure(
            self._always_active_agents(),
            scenario,
            [{"name": "透明整改", "statement": "立即道歉并公开整改。", "release_hour": 4}],
            max_rounds=2,
        )

        results = engine.run()
        rounds = results[0]

        self.assertEqual(len(rounds), 3)
        self.assertNotEqual(rounds[-1].heat, rounds[0].heat)
        self.assertTrue(any(snapshot.spoke for snapshot in rounds[-1].agent_states.values()))
        self.assertTrue(any(event.description == "媒体跟进报道" for state in rounds for event in state.key_events))
        self.assertEqual(len(round_payloads), 2)

    def test_simulation_engine_persists_multi_strategy_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project_repo = ProjectRepository(db)
            strategy_repo = StrategyRepository(db)
            round_repo = SimulationRoundRepository(db)
            project = project_repo.create("Demo", {"industry": "retail"})
            strategies = [
                {"name": "快速道歉", "statement": "立即道歉并公开整改。", "release_hour": 4},
                {"name": "延后回应", "statement": "调查完成后统一回应。", "release_hour": 8},
            ]
            strategy_records = [
                strategy_repo.create(project.id, item["name"], item["statement"], item["release_hour"])
                for item in strategies
            ]
            official_calls: list[int] = []
            engine = SimulationEngine(llm_client=self._fake_llm_client(official_calls), random_seed=3)
            engine.configure(
                self._always_active_agents(),
                ScenarioParser.parse("Demo", "零售", "舆情扩散", "正在核查", 55, -0.2),
                strategies,
                max_rounds=2,
                project_id=project.id,
                strategy_records=strategy_records,
                round_repository=round_repo,
            )

            results = engine.run()

            self.assertEqual(len(results), 2)
            self.assertEqual(len(official_calls), 2)
            for record in strategy_records:
                self.assertEqual(len(round_repo.list_by_strategy(record.id)), 3)
            db.close()

    def test_simulation_engine_skips_single_agent_failure(self) -> None:
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            if "媒体" in system or "KOL" in system:
                raise RuntimeError("model timeout")
            if "企业官方发言人" in system:
                return '{"speech": "我们公开整改。", "tone": "transparent"}'
            return (
                '{"emotion_change": 0.02, "trust_change": 0.03, '
                '"speech": "我会继续观察。", "spread_intent": 0.4, "stance_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=1)
        payloads = []
        engine.set_round_callback(lambda si, strategy, state, messages: payloads.append(messages))
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "餐饮", "舆情扩散", "核查中", 55, -0.2),
            [{"name": "透明整改", "statement": "公开整改。", "release_hour": 4}],
            max_rounds=1,
        )

        engine.run()

        flat_messages = [message for messages in payloads for message in messages]
        self.assertTrue(any(message["metrics"]["skipped"] for message in flat_messages))
        self.assertTrue(any(not message["metrics"]["skipped"] for message in flat_messages))

    def test_simulation_engine_all_agent_failure_saves_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "retail"})
            strategy = StrategyRepository(db).create(project.id, "失败策略", "声明", 4)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)

            def failing_transport(provider, messages, options):
                raise RuntimeError("provider unavailable")

            client = LLMClient(
                providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
                max_retries=0,
                transport=failing_transport,
            )
            engine = SimulationEngine(llm_client=client, random_seed=1)
            engine.configure(
                self._always_active_agents(),
                ScenarioParser.parse("Demo", "餐饮", "舆情扩散", "核查中", 55, -0.2),
                [{"name": strategy.name, "statement": strategy.statement, "release_hour": strategy.release_hour}],
                max_rounds=1,
                project_id=project.id,
                strategy_records=[strategy],
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )

            with self.assertRaises(SimulationRecoverableError):
                engine.run()

            latest = checkpoint_repo.latest_for_project(project.id)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.last_round, 1)
            db.close()

    def test_simulation_engine_resumes_from_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "retail"})
            strategy = StrategyRepository(db).create(project.id, "透明整改", "声明", 4)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "餐饮", "舆情扩散", "核查中", 55, -0.2)
            strategies = [{"name": strategy.name, "statement": strategy.statement, "release_hour": strategy.release_hour}]

            first_engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=1)
            first_engine.configure(
                self._always_active_agents(),
                scenario,
                strategies,
                max_rounds=1,
                project_id=project.id,
                strategy_records=[strategy],
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )
            first_engine.run()
            checkpoint_id = checkpoint_repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                last_round=1,
                engine_state={
                    "strategy_index": 0,
                    "last_round": 1,
                    "official_released": True,
                    "agents": [agent.to_dict() for agent in self._always_active_agents()],
                    "current_rounds": [state.to_dict() for state in first_engine.state.strategy_results[0]],
                    "strategy_results": [],
                    "scenario": scenario.to_dict(),
                    "strategies": strategies,
                    "max_rounds": 2,
                },
            )
            checkpoint = checkpoint_repo.get_by_id(checkpoint_id)

            second_engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=1)
            second_engine.configure(
                self._always_active_agents(),
                scenario,
                strategies,
                max_rounds=2,
                project_id=project.id,
                strategy_records=[strategy],
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=checkpoint,
            )
            results = second_engine.run()

            self.assertEqual(results[0][-1].round, 2)
            self.assertIsNone(checkpoint_repo.latest_for_project(project.id))
            db.close()


if __name__ == "__main__":
    unittest.main()
