from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import app_config
from core.action_feed import ActionFeed, ActionRecord
from core.agent_factory import AgentFactory
from core.document_importer import chunk_text, import_documents, render_imported_documents
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine
from core.world_state import AgentSnapshot, KeyEvent, WorldState
from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
    CheckpointRepository,
    KnowledgeRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
import llm.analysis as llm_analysis
import llm.config as llm_config
from report.exporter import ReportExporter
from report.generator import ReportGenerator, SimulationReport


class BackendModuleTests(unittest.TestCase):
    def _fake_llm_client(self) -> LLMClient:
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            user_msg = messages[1]["content"] if len(messages) > 1 else ""
            # 注意：system prompt 含全部行为体名单（互动规则），
            # 必须用画像首句识别行为体，不能用「供应商」等泛关键词
            if "你代表政府监管机构" in system:
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
            if "你是一家原材料供应商" in system:
                return (
                    '{"inventory_change": -5, "cost_change": 8, "delay_change": 1.0, '
                    '"service_change": -0.03, "margin_change": -0.04, '
                    '"pressure_change": 0.1, "risk_description": "原材料价格波动", '
                    '"response_summary": "供应商收紧供应承诺", "decision_shift": "toward_cautious"}'
                )
            if "你是一家终端零售商" in system:
                return (
                    '{"inventory_change": -10, "cost_change": -3, "delay_change": 0.2, '
                    '"service_change": 0.02, "margin_change": -0.05, '
                    '"pressure_change": 0.08, "risk_description": "促销导致利润压缩", '
                    '"response_summary": "零售商启动促销清库存", "decision_shift": "toward_aggressive"}'
                )
            if "你是一家核心制造商" in system:
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

    def test_database_repositories_round_trip(self) -> None:
        """验证 Project/Simulation/SimulationRound/Report 四个 Repository 的增删改查。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()

            project_repo = ProjectRepository(db)
            simulation_repo = SimulationRepository(db)
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
            simulation = simulation_repo.create(project.id)

            saved_round = round_repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
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
                simulation_id=simulation.id,
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
            self.assertEqual(round_repo.list_by_simulation(simulation.id)[0].inventory_level, 65.0)

            report_id = report_repo.save(
                project_id=project.id,
                title="Demo 报告",
                markdown="# Demo",
                summary={"result": "demo"},
            )
            self.assertEqual(report_repo.list_by_project(project.id)[0].id, report_id)
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

            # 空列表替换 = 清空知识库（设置页/Step1 清空入口依赖此语义）
            repo.replace_for_project(project.id, [])
            self.assertEqual(repo.list_by_project(project.id), [])
            db.close()

    def test_checkpoint_repository_round_trip(self) -> None:
        """验证仿真检查点的保存、读取、删除。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation = SimulationRepository(db).create(project.id)
            repo = CheckpointRepository(db)

            checkpoint_id = repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                last_round=2,
                engine_state={"simulation_index": 0, "last_round": 2},
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
        engine.set_round_callback(lambda state, messages: round_payloads.append((state, messages)))
        engine.configure(
            self._always_active_agents(),
            scenario,
            max_rounds=2,
        )

        rounds = engine.run()

        self.assertEqual(len(rounds), 3)
        self.assertNotEqual(rounds[-1].inventory_level, rounds[0].inventory_level)
        self.assertTrue(any(snapshot.spoke for snapshot in rounds[-1].agent_states.values()))
        self.assertEqual(len(round_payloads), 2)
        # 供应商连续两轮 delay_change=1.0 > 0.5，第 2 轮触发原材料断供
        self.assertTrue(
            any("断供" in event.description for event in rounds[-1].key_events)
        )

    def test_simulation_engine_persists_single_world_rounds(self) -> None:
        """验证单世界仿真轮次持久化到 SQLite。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project_repo = ProjectRepository(db)
            simulation_repo = SimulationRepository(db)
            round_repo = SimulationRoundRepository(db)
            project = project_repo.create("Demo", {"industry": "electronics"})
            simulation_record = simulation_repo.get_or_create_main(project.id)
            engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=3)
            engine.configure(
                self._always_active_agents(),
                ScenarioParser.parse("Demo", "电子制造", "供应链压力传导", initial_inventory=75, baseline_cost=55),
                max_rounds=2,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
            )

            rounds = engine.run()

            self.assertEqual(len(rounds), 3)
            self.assertEqual(len(round_repo.list_by_simulation(simulation_record.id)), 3)
            # 主仿真记录幂等复用，不重复创建
            self.assertEqual(simulation_repo.get_or_create_main(project.id).id, simulation_record.id)
            self.assertEqual(len(simulation_repo.list_by_project(project.id)), 1)
            db.close()

    def test_simulation_engine_skips_single_agent_failure(self) -> None:
        """验证单个行为体 LLM 调用失败时跳过而不中断仿真。"""
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            # 用画像首句识别供应商（system prompt 含全部行为体名单，泛关键词会误匹配）
            if "你是一家原材料供应商" in system:
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
        engine.set_round_callback(lambda state, messages: payloads.append(messages))
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )

        engine.run()

        flat_messages = [message for messages in payloads for message in messages]
        self.assertTrue(any(message["metrics"]["skipped"] for message in flat_messages))
        self.assertTrue(any(not message["metrics"]["skipped"] for message in flat_messages))

    def test_simulation_engine_all_agent_failure_saves_checkpoint(self) -> None:
        """验证首轮全部行为体失败时抛致命异常，后续轮次失败时可恢复。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation_record = SimulationRepository(db).get_or_create_main(project.id)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)

            # 首轮全部失败 → 致命错误
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
                max_rounds=1,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )

            with self.assertRaises(RuntimeError):
                engine.run()
            # 首轮开始前已写入初始状态检查点，致命失败后仍存在
            self.assertIsNotNone(checkpoint_repo.latest_for_project(project.id))
            db.close()

    def test_simulation_engine_resumes_from_checkpoint(self) -> None:
        """验证从检查点恢复仿真后继续运行至完成。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation_record = SimulationRepository(db).get_or_create_main(project.id)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55)

            first_engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=1)
            first_engine.configure(
                self._always_active_agents(),
                scenario,
                max_rounds=1,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )
            first_rounds = first_engine.run()
            checkpoint_id = checkpoint_repo.save(
                project_id=project.id,
                simulation_id=simulation_record.id,
                last_round=1,
                engine_state={
                    "last_round": 1,
                    "agents": [agent.to_dict() for agent in self._always_active_agents()],
                    "current_rounds": [state.to_dict() for state in first_rounds],
                    "scenario": scenario.to_dict(),
                    "seed_events": [],
                    "max_rounds": 2,
                },
            )
            checkpoint = checkpoint_repo.get_by_id(checkpoint_id)

            second_engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=1)
            second_engine.configure(
                self._always_active_agents(),
                scenario,
                max_rounds=2,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=checkpoint,
            )
            rounds = second_engine.run()

            self.assertEqual(rounds[-1].round, 2)
            self.assertIsNone(checkpoint_repo.latest_for_project(project.id))
            db.close()

    def test_world_state_serialization_round_trip(self) -> None:
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

    def test_normalize_speech(self) -> None:
        """验证行为体发言标点规范化。"""
        from core.text_utils import normalize_speech

        # 英文标点转全角（仅 CJK 语境）
        self.assertEqual(normalize_speech("库存不足,需要补货;尽快"), "库存不足，需要补货；尽快。")
        # 句末英文句号转全角
        self.assertEqual(normalize_speech("减产保价."), "减产保价。")
        # 无终止标点补句号；已有终止标点不动
        self.assertEqual(normalize_speech("降价促销"), "降价促销。")
        self.assertEqual(normalize_speech("风险可控。"), "风险可控。")
        # 非 CJK 语境不误伤（URL、英文句）
        self.assertEqual(normalize_speech("see https://a.b/c, ok."), "see https://a.b/c, ok.")
        self.assertEqual(normalize_speech(""), "")

    def test_event_detector_quiet_rounds_produce_no_events(self) -> None:
        """验证安静轮次不产生事件（自然恢复不作为关键事件）。"""
        from core.events import EventDetector

        detector = EventDetector()
        for round_index in range(1, 6):
            events = detector.detect(WorldState(round=round_index, simulated_hour=round_index))
            self.assertEqual(events, [])

        # 供应商连续 2 轮延迟 → 触发原材料断供
        detector = EventDetector()
        detector.detect(
            WorldState(round=1, simulated_hour=1), supplier_delayed=True
        )
        events = detector.detect(
            WorldState(round=2, simulated_hour=2), supplier_delayed=True
        )
        self.assertEqual([e.event_type for e in events], ["raw_material_shortage"])

    def test_action_feed_visibility_rules(self) -> None:
        """验证行动信息流的邻居可见性、高影响力广播与自身排除。"""
        feed = ActionFeed()
        feed.append([
            ActionRecord(round=1, agent_id=1, agent_name="原材料供应商", role="上游供应商",
                         action_type="adjust_supply", content="收紧供应", influence=1.0),
            ActionRecord(round=1, agent_id=2, agent_name="制造商", role="核心制造商",
                         action_type="adjust_capacity", content="减产保价", influence=2.5),
            ActionRecord(round=1, agent_id=5, agent_name="物流服务商", role="物流支撑方",
                         action_type="expedite_logistics", content="加急配送", influence=1.2),
        ])
        # 制造商：供应商是邻居（低影响力也可见），自身行动排除，物流非邻居且低于广播阈值
        self.assertEqual([r.agent_id for r in feed.for_agent(agent_id=2, neighbor_ids={1})], [1])
        # 零售商：无邻居关系时只有高影响力广播（制造商 2.5）可见
        self.assertEqual([r.agent_id for r in feed.for_agent(agent_id=4, neighbor_ids=set())], [2])
        # 供应商：制造商既是邻居又是高影响力，去重后只出现一次
        self.assertEqual([r.agent_id for r in feed.for_agent(agent_id=1, neighbor_ids={2})], [2])
        self.assertEqual(ActionFeed().for_agent(1, set()), [])

    def test_action_type_validation_and_fallback(self) -> None:
        """验证 action_type 越权降级与 reaction_to 透传。"""
        def fake_transport(provider, messages, options):
            return (
                '{"action_type": "adjust_price", "reaction_to": "制造商", '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "尝试调价", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=1)
        payloads = []
        engine.set_round_callback(lambda state, messages: payloads.append(messages))
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )
        engine.run()

        by_name = {m["agent_name"]: m for messages in payloads for m in messages}
        # 零售商允许 adjust_price → 保留并透传回应对象；监管越权 → 降级 maintain 并记 warning
        self.assertEqual(by_name["零售商"]["action_type"], "adjust_price")
        self.assertEqual(by_name["零售商"]["reaction_to"], "制造商")
        self.assertEqual(by_name["监管机构"]["action_type"], "maintain")
        self.assertIn("降级", by_name["监管机构"]["metrics"]["warning"])

    def test_interaction_observation_reaches_next_round(self) -> None:
        """验证跨轮反应链：第 2 轮行为体的 prompt 包含第 1 轮邻居的行动。"""
        seen_systems: list[str] = []

        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            seen_systems.append(system)
            if "你是一家原材料供应商" in system:
                return (
                    '{"action_type": "adjust_supply", "reaction_to": "none", '
                    '"inventory_change": -5, "cost_change": 8, "delay_change": 1.0, '
                    '"service_change": -0.03, "margin_change": -0.04, "pressure_change": 0.1, '
                    '"risk_description": "原材料价格波动", '
                    '"response_summary": "供应商收紧供应承诺", "decision_shift": "none"}'
                )
            return (
                '{"action_type": "maintain", "reaction_to": "none", '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "正常运作", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=7)
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=2,
        )
        engine.run()

        # 无节点场景走兜底主链：供应商是制造商的上游邻居，
        # 其第 1 轮行动应出现在制造商第 2 轮的 system prompt 中
        # （用画像首行识别制造商自身的 prompt，避免匹配到他人观察里的制造商条目）
        manufacturer_systems = [s for s in seen_systems if "你是一家核心制造商" in s]
        self.assertEqual(len(manufacturer_systems), 2)
        self.assertNotIn("供应商收紧供应承诺", manufacturer_systems[0])
        self.assertIn("供应商收紧供应承诺", manufacturer_systems[1])
        self.assertIn("上游", manufacturer_systems[1])

    def test_seed_events_injected_into_observation(self) -> None:
        """验证种子事件在指定轮次注入信息流，当轮起即可被行为体观察。"""
        seen_prompts: list[str] = []

        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            user_msg = messages[1]["content"] if len(messages) > 1 else ""
            seen_prompts.append(system + "\n" + user_msg)
            return (
                '{"action_type": "maintain", "reaction_to": "none", '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "正常运作", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=7)
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            seed_events=[{"content": "港口罢工导致物流中断", "cycle": 2}],
            max_rounds=2,
        )
        engine.run()

        # 7 个行为体全部激活：前 7 次调用为第 1 轮，后 7 次为第 2 轮
        self.assertEqual(len(seen_prompts), 14)
        round_one, round_two = seen_prompts[:7], seen_prompts[7:]
        self.assertTrue(all("港口罢工导致物流中断" not in prompt for prompt in round_one))
        self.assertTrue(all("港口罢工导致物流中断" in prompt for prompt in round_two))
        # 信息流中 agent_id=0 的种子事件以环境事件格式渲染进观察条目（标注不可回应）
        self.assertTrue(any("世界事件" in prompt and "不可作为回应对象" in prompt for prompt in round_two))

    def test_knowledge_context_reaches_agent_prompt(self) -> None:
        """RAG 接线：知识库内容经引擎线程串行检索进入行为体 prompt。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            KnowledgeRepository(db).replace_for_project(project.id, [
                {"source": "case.md", "chunk_index": 0,
                 "content": "华东港口 汛期 物流 管制 原材料 交付 延迟"},
            ])

            seen_users: list[str] = []

            def fake_transport(provider, messages, options):
                seen_users.append(messages[1]["content"])
                return (
                    '{"action_type": "maintain", "reaction_to": "none", '
                    '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                    '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                    '"risk_description": "", "response_summary": "正常运作", "decision_shift": "none"}'
                )

            client = LLMClient(
                providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
                max_retries=0,
                transport=fake_transport,
            )
            engine = SimulationEngine(llm_client=client, random_seed=1)
            engine.configure(
                self._always_active_agents(),
                ScenarioParser.parse("Demo", "电子制造", "供应链压力 原材料 交付", initial_inventory=75, baseline_cost=55),
                max_rounds=1,
                project_id=project.id,
                knowledge_repository=KnowledgeRepository(db),
            )
            engine.run()

            # 检索命中后，知识块原文应出现在 user message 的 knowledge_context 段
            self.assertTrue(any("华东港口" in u for u in seen_users))
            db.close()

    def test_agent_factory_apply_overrides(self) -> None:
        """验证按行为体 id 的性格覆盖生效，未覆盖行为体保持模板默认。"""
        agents = AgentFactory.create_all()
        template = AgentFactory.get_template(1)

        result = AgentFactory.apply_overrides(
            agents,
            {"4": {"stance": "cautious", "activity": 0.1, "profile": "自定义画像"}},
        )

        self.assertIs(result, agents)
        overridden = next(agent for agent in agents if agent.id == 4)
        self.assertEqual(overridden.decision_stance, "cautious")
        self.assertEqual(overridden.base_stance, "cautious")
        self.assertEqual(overridden.activity, 0.1)
        self.assertEqual(overridden.profile, "自定义画像")

        untouched = next(agent for agent in agents if agent.id == 1)
        self.assertEqual(untouched.decision_stance, template["decision_stance"])
        self.assertEqual(untouched.base_stance, template["decision_stance"])
        self.assertEqual(untouched.activity, template["activity"])
        self.assertEqual(untouched.profile, template["profile"])

        self.assertIs(AgentFactory.apply_overrides(agents, None), agents)

    def test_reaction_to_validation_and_fallback(self) -> None:
        """reaction_to 只保留合法行为体名：多目标取首个，节点名/世界事件/自身降级 none。"""
        def fake_transport(provider, messages, options):
            system = messages[0]["content"]
            if "核心制造商" in system:
                reaction = '"世界事件"'              # 环境事件 → none
            elif "终端零售商" in system:
                reaction = '"制造商、分销商"'        # 多目标 → 取首个合法
            elif "政府监管机构" in system:
                reaction = '"自营门店"'              # 场景节点名 → none
            elif "原材料供应商。你关注" in system:
                reaction = '"原材料供应商"'          # 自身 → none
            else:
                reaction = '"none"'
            return (
                '{"action_type": "maintain", "reaction_to": ' + reaction + ', '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "正常运作", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=1)
        payloads = []
        engine.set_round_callback(lambda state, messages: payloads.append(messages))
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )
        engine.run()

        by_name = {m["agent_name"]: m for messages in payloads for m in messages}
        self.assertEqual(by_name["制造商"]["reaction_to"], "none")
        self.assertIn("降级", by_name["制造商"]["metrics"]["warning"])
        self.assertEqual(by_name["零售商"]["reaction_to"], "制造商")
        self.assertIn("多个对象", by_name["零售商"]["metrics"]["warning"])
        self.assertEqual(by_name["监管机构"]["reaction_to"], "none")
        self.assertEqual(by_name["原材料供应商"]["reaction_to"], "none")
        self.assertEqual(by_name["分销商"]["reaction_to"], "none")
        self.assertEqual(by_name["分销商"]["metrics"]["warning"], "")

    def test_feed_marks_seed_not_reactable_and_recalls_own_speech(self) -> None:
        """种子事件条目标注不可回应；last_entry_for 回显自身上轮发言并进入 prompt。"""
        feed = ActionFeed()
        feed.append([
            ActionRecord(
                round=1, agent_id=0, agent_name="世界事件", role="外部干预",
                action_type="seed", content="港口罢工导致物流中断", influence=2.5,
            ),
            ActionRecord(
                round=1, agent_id=2, agent_name="制造商", role="核心制造商",
                action_type="adjust_supply", content="制造商上轮发言内容",
            ),
        ])
        seed_entry = feed._records[0].format_entry()
        self.assertIn("不可作为回应对象", seed_entry)
        self.assertNotIn("【seed】", seed_entry)
        self.assertEqual(feed.last_entry_for(2).content, "制造商上轮发言内容")
        self.assertIsNone(feed.last_entry_for(3))

        # 端到端：第 2 轮制造商的 system prompt 包含其上轮发言与互动规则
        seen_systems: list[str] = []

        def fake_transport(provider, messages, options):
            seen_systems.append(messages[0]["content"])
            return (
                '{"action_type": "maintain", "reaction_to": "none", '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "本轮新发言", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=7)
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=2,
        )
        engine.run()

        manufacturer_systems = [s for s in seen_systems if "你是一家核心制造商" in s]
        self.assertEqual(len(manufacturer_systems), 2)
        self.assertIn("（首轮，暂无上轮发言）", manufacturer_systems[0])
        self.assertIn("本轮新发言", manufacturer_systems[1])
        self.assertIn("不可回应", manufacturer_systems[1])
        self.assertIn("禁止编造具体数量", manufacturer_systems[1])

    def test_observation_collapses_repeated_actions(self) -> None:
        """观察层：同一行为体相邻轮次内容高度相似时折叠旧条目为「持续中」。"""
        engine = SimulationEngine(llm_client=self._fake_llm_client(), random_seed=1)
        agents = self._always_active_agents()
        engine.configure(
            agents,
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )
        repeated = "小幅提升排产量，动态跟踪上游供应变化，灵活调整排产节奏，保障交付履约。"
        feed = ActionFeed()
        feed.append([
            ActionRecord(
                round=1, agent_id=1, agent_name="原材料供应商", role="上游供应商",
                action_type="adjust_supply", content=repeated,
            ),
            ActionRecord(
                round=2, agent_id=1, agent_name="原材料供应商", role="上游供应商",
                action_type="adjust_supply", content=repeated + "略有调整",
            ),
        ])

        manufacturer = next(a for a in agents if a.id == 2)
        observation = engine._build_observation(manufacturer, agents, feed, WorldState())

        self.assertIn("持续中", observation)
        self.assertEqual(observation.count(repeated), 1)  # 旧条目被折叠，只出现一次

        # 内容差异大时不折叠
        feed2 = ActionFeed()
        feed2.append([
            ActionRecord(
                round=1, agent_id=1, agent_name="原材料供应商", role="上游供应商",
                action_type="adjust_supply", content="收紧供应承诺，优先保障核心客户。",
            ),
            ActionRecord(
                round=2, agent_id=1, agent_name="原材料供应商", role="上游供应商",
                action_type="reduce_orders", content="因环保限产大幅削减非优先级订单接收。",
            ),
        ])
        observation2 = engine._build_observation(manufacturer, agents, feed2, WorldState())
        self.assertNotIn("持续中", observation2)

    def test_decision_temperature_from_config(self) -> None:
        """行为体决策温度取自 app_config.llm.decision_temperature。"""
        seen_options: list[dict] = []

        def fake_transport(provider, messages, options):
            seen_options.append(options)
            return (
                '{"action_type": "maintain", "reaction_to": "none", '
                '"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
                '"service_change": 0.01, "margin_change": 0.01, "pressure_change": 0.0, '
                '"risk_description": "", "response_summary": "正常运作", "decision_shift": "none"}'
            )

        client = LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "gpt-4o-mini", "key")],
            max_retries=0,
            transport=fake_transport,
        )
        engine = SimulationEngine(llm_client=client, random_seed=1)
        engine.configure(
            self._always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )
        with mock.patch.object(app_config.llm, "decision_temperature", 0.5):
            engine.run()

        self.assertTrue(seen_options)
        self.assertTrue(all(o["temperature"] == 0.5 for o in seen_options))

    def test_report_save_or_update_latest(self) -> None:
        """save_or_update_latest：首次插入，再次调用更新同一行，reports 表不膨胀。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {})
            repo = ReportRepository(db)

            first_id = repo.save_or_update_latest(
                project_id=project.id, title="报告", markdown="v1", summary={"n": 1}
            )
            second_id = repo.save_or_update_latest(
                project_id=project.id, title="报告", markdown="v2",
                summary={"n": 2, "ai_analysis": {"evolution_analysis": "x"}},
            )

            self.assertEqual(first_id, second_id)
            reports = repo.list_by_project(project.id)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].markdown, "v2")
            self.assertEqual(reports[0].summary["n"], 2)
            db.close()

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


class AIIntegrationTests(unittest.TestCase):
    """v0.3 全链路 AI 集成：全局配置、文档抽取、行为体生成、演化分析。"""

    @staticmethod
    def _json_client(payload: str) -> LLMClient:
        return LLMClient(
            providers=[ProviderSettings(LLMProvider.OPENAI, "test-model", "key")],
            max_retries=0,
            transport=lambda provider, messages, options: payload,
        )

    def test_vendor_state_persist_and_reload(self) -> None:
        """厂商配置写入 .env 并可从环境变量读回，生效厂商可切换。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            state = {
                2: {"key": "kimi-key", "url": "https://api.moonshot.cn/v1", "model": "kimi-k2"},
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                llm_config.persist_vendor_state(state, active_vendor=2, env_path=env_path)
                env_text = env_path.read_text(encoding="utf-8")
                self.assertIn("KIMI_API_KEY=", env_text)
                self.assertIn("kimi-key", env_text)
                self.assertEqual(llm_config.get_active_vendor(), 2)

                reloaded = llm_config.load_vendor_state()
                self.assertEqual(reloaded[2]["key"], "kimi-key")
                self.assertEqual(reloaded[2]["model"], "kimi-k2")

                settings = llm_config.get_active_provider_settings()
                self.assertIsNotNone(settings)
                self.assertEqual(settings.provider, LLMProvider.OPENAI)
                self.assertEqual(settings.api_key, "kimi-key")

    def test_build_llm_client_without_key_returns_none(self) -> None:
        """未配置任何 API Key 时 build_llm_client 返回 None（AI 功能降级）。"""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llm_config.get_active_provider_settings())
            self.assertIsNone(llm_config.build_llm_client())

    def test_persist_env_vars(self) -> None:
        """persist_env_vars：任意键值写入 .env 并同步当前进程环境变量。"""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            with mock.patch.dict(os.environ, {}, clear=True):
                llm_config.persist_env_vars(
                    {"SIM_MAX_ROUNDS": "16", "LLM_DECISION_TEMPERATURE": "0.5"},
                    env_path=env_path,
                )
                self.assertEqual(os.environ["SIM_MAX_ROUNDS"], "16")
                env_text = env_path.read_text(encoding="utf-8")
                self.assertIn("SIM_MAX_ROUNDS", env_text)
                self.assertIn("16", env_text)
                self.assertIn("LLM_DECISION_TEMPERATURE", env_text)

    def test_extract_scenario_from_docs_validates_fields(self) -> None:
        """文档抽取：非法节点类型/越界数值被修正，背景为空时报错。"""
        payload = (
            '{"title": "电子产品供应链", "industry": "电子制造", '
            '"background": "以华南制造商为核心的四级供应链。", '
            '"nodes": ['
            '{"name": "芯片供应商", "type": "supplier", "inventory": 80, "lead_time": 2, '
            '"capacity": 100, "cost_index": 52, "downstream": ["制造商"]}, '
            '{"name": "坏节点", "type": "hacker", "inventory": 999, "lead_time": -3, '
            '"capacity": 0, "cost_index": 200}, '
            '{"name": "", "type": "retailer"}], '
            '"initial_inventory": 120, "baseline_cost": -5, "baseline_service_level": 1.5}'
        )
        result = llm_analysis.extract_scenario_from_docs(
            self._json_client(payload), "某电子产品供应链文档内容"
        )

        self.assertEqual(result["title"], "电子产品供应链")
        self.assertEqual(len(result["nodes"]), 2)  # 空名节点被过滤
        bad = result["nodes"][1]
        self.assertEqual(bad["type"], "supplier")  # 非法类型回退
        self.assertEqual(bad["inventory"], 100)    # clamp 到上限
        self.assertEqual(bad["lead_time"], 0)
        self.assertEqual(result["initial_inventory"], 100)
        self.assertEqual(result["baseline_cost"], 0)
        self.assertEqual(result["baseline_service_level"], 1.0)

        with self.assertRaises(ValueError):
            llm_analysis.extract_scenario_from_docs(self._json_client("{}"), "文档")
        with self.assertRaises(ValueError):
            llm_analysis.extract_scenario_from_docs(self._json_client(payload), "")

    def test_generate_agent_config_validates_and_truncates(self) -> None:
        """行为体生成：非法 stance 回退模板默认，7 个行为体齐全，种子事件截断到 3 条。"""
        agents_config = {
            str(i): {"stance": "aggressive", "activity": 0.5, "influence": 1.0, "profile": f"画像{i}"}
            for i in range(1, 8)
        }
        agents_config["1"]["stance"] = "reckless"      # 非法，应回退
        agents_config["2"]["activity"] = 9.9           # 越界，应 clamp
        seeds = [{"content": f"事件{i}", "cycle": i} for i in range(1, 6)]
        payload = json.dumps(
            {"agents_config": agents_config, "seed_events": seeds},
            ensure_ascii=False,
        )

        result = llm_analysis.generate_agent_config(
            self._json_client(payload), {"title": "t", "background": "b", "nodes": []}
        )

        self.assertEqual(len(result["agents_config"]), 7)
        template_1 = AgentFactory.get_template(1)
        self.assertEqual(result["agents_config"]["1"]["stance"], template_1["decision_stance"])
        self.assertEqual(result["agents_config"]["2"]["activity"], 1.0)
        self.assertEqual(len(result["seed_events"]), 3)
        self.assertEqual(result["seed_events"][0]["content"], "事件1")

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
            self._json_client(payload), report, []
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
