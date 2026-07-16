from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.agent_factory import AgentFactory
from core.document_importer import chunk_text, import_documents, render_imported_documents
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine
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
    def _fake_llm_client(self) -> LLMClient:
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            user_msg = messages[1]["content"] if len(messages) > 1 else ""
            if "监管机构" in system or "监管方" in system:
                if "风险" in user_msg:
                    return (
                        '{"inventory_change": 0, "cost_change": 5, "delay_change": 0.5, '
                        '"service_change": -0.02, "margin_change": -0.04, '
                        '"pressure_change": 0.05, "risk_description": "存在合规风险需关注", '
                        '"response_summary": "监管机构关注合规问题", "decision_shift": "toward_defensive"}'
                    )
                return (
                    '{"inventory_change": 0, "cost_change": 0, "delay_change": 0, '
                    '"service_change": 0, "margin_change": 0, '
                    '"pressure_change": 0.0, "risk_description": "", '
                    '"response_summary": "监管机构保持关注", "decision_shift": "none"}'
                )
            if "供应商" in system:
                return (
                    '{"inventory_change": -5, "cost_change": 8, "delay_change": 1.0, '
                    '"service_change": -0.03, "margin_change": -0.04, '
                    '"pressure_change": 0.1, "risk_description": "原材料价格波动", '
                    '"response_summary": "供应商收紧供应承诺", "decision_shift": "toward_cautious"}'
                )
            if "零售商" in system:
                return (
                    '{"inventory_change": -10, "cost_change": -3, "delay_change": 0.2, '
                    '"service_change": 0.02, "margin_change": -0.05, '
                    '"pressure_change": 0.08, "risk_description": "促销导致利润压缩", '
                    '"response_summary": "零售商启动促销清库存", "decision_shift": "toward_aggressive"}'
                )
            if "制造商" in system:
                return (
                    '{"inventory_change": 3, "cost_change": 2, "delay_change": -0.5, '
                    '"service_change": 0.05, "margin_change": 0.03, '
                    '"pressure_change": -0.05, "risk_description": "", '
                    '"response_summary": "制造商协调上下游", "decision_shift": "toward_cooperative"}'
                )
            return (
                '{"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, '
                '"pressure_change": 0.0, "risk_description": "", '
                '"response_summary": "正常运作", "decision_shift": "none"}'
            )

        return LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )

    def _always_active_agents(self):
        agents = AgentFactory.create_all()
        for agent in agents:
            agent.activity = 1.0
            agent.active_cycles = list(range(1, 13))
        return agents

    def test_agent_count_is_seven(self) -> None:
        """验证供应链行为体数量为7。"""
        agents = AgentFactory.create_all()
        self.assertEqual(len(agents), 7)

    def test_database_repositories_round_trip(self) -> None:
        """验证 Project/Strategy/SimulationRound/Report 四个 Repository 的增删改查。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()

            project_repo = ProjectRepository(db)
            strategy_repo = StrategyRepository(db)
            round_repo = SimulationRoundRepository(db)
            report_repo = ReportRepository(db)

            project = project_repo.create("Demo", {"industry": "electronics"})
            project = project_repo.update_scenario(
                project.id,
                {"title": "电子产品供应链", "industry": "electronics", "initial_inventory": 80},
                name="电子产品供应链",
            )
            self.assertEqual(project.name, "电子产品供应链")
            self.assertEqual(project.scenario["industry"], "electronics")
            strategy = strategy_repo.create(
                project.id,
                name="激进补货",
                actor="零售商",
                decision="增加安全库存至150%",
                release_cycle="1-6",
            )

            saved_round = round_repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                service_level=0.82,
                profit_margin=0.12,
                resilience_score=58.0,
                state={"key_events": ["需求激增"]},
                agent_messages=[
                    {
                        "agent_name": "零售商",
                        "decision_stance": "aggressive",
                        "content": "启动促销活动。",
                    }
                ],
            )
            updated_round = round_repo.save(
                project_id=project.id,
                strategy_id=strategy.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=65.0,
                cost_index=58.0,
                delivery_delay=0.8,
                service_level=0.80,
                profit_margin=0.10,
                resilience_score=55.0,
                state={"key_events": ["需求激增"]},
            )

            self.assertEqual(saved_round.id, updated_round.id)
            self.assertEqual(round_repo.list_by_strategy(strategy.id)[0].inventory_level, 65.0)

            report_id = report_repo.save(
                project_id=project.id,
                title="Demo 报告",
                markdown="# Demo",
                html="<h1>Demo</h1>",
                summary={"winner": "激进补货"},
            )
            self.assertEqual(report_repo.list_by_project(project.id)[0].id, report_id)
            db.close()

    def test_strategy_replace_for_project(self) -> None:
        """验证方案批量替换（删除旧记录后重建）。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            repo = StrategyRepository(db)
            repo.create(project.id, "旧方案", "制造商", "旧决策", "1-4")

            saved = repo.replace_for_project(
                project.id,
                [
                    {"name": "激进补货", "actor": "零售商", "decision": "增加安全库存。", "release_cycle": "1-6", "parameters": {}},
                    {"name": "保守观望", "actor": "制造商", "decision": "维持排产。", "release_cycle": "1-12", "parameters": {}},
                    {"name": "混合方案", "actor": "分销商", "decision": "动态调整。", "release_cycle": "3-8", "parameters": {}},
                ],
            )

            self.assertEqual(len(saved), 3)
            self.assertEqual([item.name for item in repo.list_by_project(project.id)], ["激进补货", "保守观望", "混合方案"])
            db.close()

    def test_document_importer_reads_text_documents_with_limits(self) -> None:
        """验证文档导入、分块和字数限制。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "background.md"
            path.write_text("# 供应链背景\n\n电子产品供应链面临原材料涨价压力。", encoding="utf-8")

            imported = import_documents([path], max_total_chars=20)
            rendered = render_imported_documents(imported)
            chunks = chunk_text(imported[0].text, max_chars=8, overlap=2)

            self.assertEqual(len(imported), 1)
            self.assertIn("background.md", rendered)
            self.assertLessEqual(len(imported[0].text), 20)
            self.assertGreaterEqual(len(chunks), 2)

    def test_knowledge_repository_replace_and_search(self) -> None:
        """验证知识库片段的替换和关键词搜索。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            repo = KnowledgeRepository(db)

            repo.replace_for_project(
                project.id,
                [
                    {"source": "a.md", "chunk_index": 0, "content": "原材料 价格 波动 供应商 产能"},
                    {"source": "b.md", "chunk_index": 0, "content": "物流 运输 仓储 配送"},
                ],
            )
            hits = repo.search(project.id, "原材料价格供应商产能", limit=1)

            self.assertEqual(len(repo.list_by_project(project.id)), 2)
            self.assertEqual(hits[0].source, "a.md")
            db.close()

    def test_checkpoint_repository_round_trip(self) -> None:
        """验证仿真检查点的保存、读取、删除。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            strategy = StrategyRepository(db).create(project.id, "激进补货", "零售商", "增加安全库存", "1-6")
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
        """验证 LLM 多厂商 fallback 和 JSON 修复解析。"""
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
        """验证自定义兼容 API 地址（如 DeepSeek）。"""
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
        """验证报告生成和 Markdown/HTML 导出。"""
        generator = ReportGenerator(
            project_name="Prism",
            scenario_background="电子产品供应链推演",
        )
        generator.add_strategy_result(
            "激进补货",
            "增加安全库存至150%",
            [
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
                ),
            ],
        )
        report = generator.generate()
        markdown = ReportExporter.to_markdown(report)
        html = ReportExporter.export_html(report)

        self.assertEqual(report.winner, "激进补货")
        self.assertIn("激进补货", markdown)
        self.assertIn("<h1", html)
        self.assertIn("供应链决策推演报告", markdown)

    def test_simulation_engine_runs_llm_rounds_and_events(self) -> None:
        """验证仿真引擎 LLM 多轮运行和事件检测。"""
        scenario = ScenarioParser.parse(
            title="Demo 供应链",
            industry="电子制造",
            background="原材料涨价压力正在传导。",
            initial_inventory=75,
            baseline_cost=55,
            baseline_service_level=0.80,
        )
        engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=7)
        round_payloads = []
        engine.set_round_callback(lambda si, strategy, state, messages: round_payloads.append((state, messages)))
        engine.configure(
            self._always_active_agents(),
            scenario,
            [{"name": "激进补货", "actor": "零售商", "decision": "增加安全库存至150%", "release_cycle": "1-6"}],
            max_rounds=2,
        )

        results = engine.run()
        rounds = results[0]

        self.assertEqual(len(rounds), 3)
        self.assertNotEqual(rounds[-1].inventory_level, rounds[0].inventory_level)
        self.assertTrue(any(snapshot.spoke for snapshot in rounds[-1].agent_states.values()))
        self.assertEqual(len(round_payloads), 2)

    def test_simulation_engine_persists_multi_strategy_rounds(self) -> None:
        """验证多方案仿真轮次持久化到 SQLite。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project_repo = ProjectRepository(db)
            strategy_repo = StrategyRepository(db)
            round_repo = SimulationRoundRepository(db)
            project = project_repo.create("Demo", {"industry": "electronics"})
            strategies = [
                {"name": "激进补货", "actor": "零售商", "decision": "增加安全库存。", "release_cycle": "1-6"},
                {"name": "保守观望", "actor": "制造商", "decision": "维持排产。", "release_cycle": "1-12"},
            ]
            strategy_records = [
                strategy_repo.create(project.id, item["name"], item["actor"], item["decision"], item["release_cycle"])
                for item in strategies
            ]
            engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=3)
            engine.configure(
                self._always_active_agents(),
                ScenarioParser.parse("Demo", "电子制造", "供应链压力传导", initial_inventory=75, baseline_cost=55),
                strategies,
                max_rounds=2,
                project_id=project.id,
                strategy_records=strategy_records,
                round_repository=round_repo,
            )

            results = engine.run()

            self.assertEqual(len(results), 2)
            for record in strategy_records:
                self.assertEqual(len(round_repo.list_by_strategy(record.id)), 3)
            db.close()

    def test_simulation_engine_skips_single_agent_failure(self) -> None:
        """验证单个行为体 LLM 调用失败时跳过而不中断仿真。"""
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            if "供应商" in system:
                raise RuntimeError("model timeout")
            return (
                '{"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, '
                '"pressure_change": 0.0, "risk_description": "", '
                '"response_summary": "正常运作", "decision_shift": "none"}'
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
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            [{"name": "激进补货", "actor": "", "decision": "增加安全库存。", "release_cycle": "1-6"}],
            max_rounds=1,
        )

        engine.run()

        flat_messages = [message for messages in payloads for message in messages]
        self.assertTrue(any(message["metrics"]["skipped"] for message in flat_messages))
        self.assertTrue(any(not message["metrics"]["skipped"] for message in flat_messages))

    def test_simulation_engine_all_agent_failure_saves_checkpoint(self) -> None:
        """验证全部行为体失败时保存检查点并抛出异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            strategy = StrategyRepository(db).create(project.id, "失败方案", "零售商", "失败决策", "1-4")
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
                ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
                [{"name": strategy.name, "actor": strategy.actor, "decision": strategy.decision, "release_cycle": strategy.release_cycle}],
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
        """验证从检查点恢复仿真后继续运行至完成。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            strategy = StrategyRepository(db).create(project.id, "激进补货", "零售商", "增加安全库存", "1-6")
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55)
            strategies = [{"name": strategy.name, "actor": strategy.actor, "decision": strategy.decision, "release_cycle": strategy.release_cycle}]

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

    def test_world_state_new_fields_round_trip(self) -> None:
        """验证 WorldState 供应链字段的序列化。"""
        ws = WorldState(
            round=3,
            simulated_hour=3,
            inventory_level=65.0,
            cost_index=58.0,
            delivery_delay=1.5,
            service_level=0.78,
            profit_margin=0.08,
            resilience_score=55.0,
            key_events=[
                KeyEvent(
                    round=3,
                    simulated_hour=3,
                    event_type="raw_material_shortage",
                    description="原材料断供",
                    inventory_delta=-20.0,
                    cost_delta=15.0,
                    delay_delta=2.0,
                )
            ],
        )
        d = ws.to_dict()
        restored = WorldState.from_dict(d)
        self.assertEqual(restored.inventory_level, 65.0)
        self.assertEqual(restored.cost_index, 58.0)
        self.assertEqual(restored.delivery_delay, 1.5)
        self.assertEqual(restored.service_level, 0.78)
        self.assertEqual(restored.profit_margin, 0.08)
        self.assertEqual(restored.resilience_score, 55.0)
        self.assertEqual(len(restored.key_events), 1)
        self.assertEqual(restored.key_events[0].event_type, "raw_material_shortage")


if __name__ == "__main__":
    unittest.main()
