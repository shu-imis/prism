from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from config import app_config
from core.action_feed import ActionFeed, ActionRecord
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine
from core.world_state import WorldState
from db.database import Database
from db.models import (
    ProjectRepository,
    SimulationRepository,
    SimulationRoundRepository,
    CheckpointRepository,
    KnowledgeRepository,
)
from llm.client import LLMClient, LLMProvider, ProviderSettings
from tests.helpers import make_always_active_agents, make_fake_llm_client


class SimulationEngineTests(unittest.TestCase):
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
        engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=7)
        round_payloads = []
        engine.set_round_callback(lambda state, messages: round_payloads.append((state, messages)))
        engine.configure(
            make_always_active_agents(),
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
            engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=3)
            engine.configure(
                make_always_active_agents(),
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
            make_always_active_agents(),
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
                make_always_active_agents(),
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
        """验证从检查点恢复仿真后继续运行至完成，且以检查点保存的 max_rounds 为上界。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation_record = SimulationRepository(db).get_or_create_main(project.id)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55)

            first_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            first_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=1,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )
            first_rounds = first_engine.run()
            # 检查点记录了保存时的 max_rounds=2，之后配置被改大到 5
            checkpoint_id = checkpoint_repo.save(
                project_id=project.id,
                simulation_id=simulation_record.id,
                last_round=1,
                engine_state={
                    "last_round": 1,
                    "agents": [agent.to_dict() for agent in make_always_active_agents()],
                    "current_rounds": [state.to_dict() for state in first_rounds],
                    "scenario": scenario.to_dict(),
                    "seed_events": [],
                    "max_rounds": 2,
                },
            )
            checkpoint = checkpoint_repo.get_by_id(checkpoint_id)

            second_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            second_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=5,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=checkpoint,
            )
            rounds = second_engine.run()

            # 只补跑到检查点记录的第 2 轮即完成，而非按新配置跑到第 5 轮
            self.assertEqual(rounds[-1].round, 2)
            self.assertIsNone(checkpoint_repo.latest_for_project(project.id))
            db.close()

    def test_simulation_engine_round_timeout_skips_slow_agent(self) -> None:
        """验证单轮超时后慢行为体被跳过，且引擎不阻塞等待其 LLM 调用结束。"""
        engine = SimulationEngine(
            llm_client=make_fake_llm_client(slow_supplier_seconds=5), random_seed=1
        )
        payloads = []
        engine.set_round_callback(lambda state, messages: payloads.append(messages))
        engine.configure(
            make_always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
            round_timeout=1,
        )

        started = time.monotonic()
        engine.run()
        elapsed = time.monotonic() - started

        # 总耗时远小于慢行为体的 5 秒睡眠，证明超时后未 shutdown(wait=True) 阻塞
        self.assertLess(elapsed, 4)
        flat_messages = [message for messages in payloads for message in messages]
        self.assertTrue(any(
            message["metrics"]["skipped"]
            and message["metrics"]["warning"] == "round_timeout"
            for message in flat_messages
        ))
        self.assertTrue(any(not message["metrics"]["skipped"] for message in flat_messages))

    def test_simulation_engine_salvages_finished_future_on_timeout(self) -> None:
        """验证超时瞬间已完成但未出队的 future 结果被取回，而非静默丢弃。"""
        import core.simulation_engine as engine_module

        def fake_as_completed(futures, timeout=None):
            # 快行为体立即完成、慢行为体仍在睡眠：等快的结果就绪后直接抛超时，
            # 确定性复现"超时瞬间已完成但未 yield"的窗口
            time.sleep(0.5)
            raise TimeoutError()

        engine = SimulationEngine(
            llm_client=make_fake_llm_client(slow_supplier_seconds=5), random_seed=1
        )
        payloads = []
        engine.set_round_callback(lambda state, messages: payloads.append(messages))
        engine.configure(
            make_always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
            round_timeout=1,
        )

        with mock.patch.object(engine_module, "as_completed", fake_as_completed):
            engine.run()

        flat_messages = [message for messages in payloads for message in messages]
        skipped = [m for m in flat_messages if m["metrics"]["skipped"]]
        done = [m for m in flat_messages if not m["metrics"]["skipped"]]
        # 慢行为体被跳过，其余 6 个已完成行为体的发言全部 salvage 进轮次数据
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["metrics"]["warning"], "round_timeout")
        self.assertEqual(len(done), 6)

    def test_checkpoint_stores_last_state_only_and_resumes(self) -> None:
        """验证检查点只存最新轮次快照，恢复时从轮次表重建完整历史。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation_record = SimulationRepository(db).get_or_create_main(project.id)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55)

            # 跑完第 1 轮后中断，触发检查点落库
            first_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            first_engine.set_round_callback(
                lambda state, messages: first_engine.abort() if state.round == 1 else None
            )
            first_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=3,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )
            first_engine.run()

            checkpoint = checkpoint_repo.latest_for_project(project.id)
            self.assertIsNotNone(checkpoint)
            engine_state = checkpoint.engine_state
            # 检查点瘦身：只存最新一份快照与检测器计数，不再内嵌全部历史轮次
            self.assertIn("last_state", engine_state)
            self.assertIn("detector", engine_state)
            self.assertNotIn("current_rounds", engine_state)

            second_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            second_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=3,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=checkpoint,
            )
            rounds = second_engine.run()

            # 从轮次表重建历史（第 0、1 轮）后续跑至第 3 轮完成，轮次连续
            self.assertEqual([state.round for state in rounds], [0, 1, 2, 3])
            self.assertIsNone(checkpoint_repo.latest_for_project(project.id))
            db.close()

    def test_event_detector_counts_survive_checkpoint_resume(self) -> None:
        """验证事件检测器连续计数随检查点续传：断点前后各一轮供应商延迟即触发断供。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation_record = SimulationRepository(db).get_or_create_main(project.id)
            round_repo = SimulationRoundRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            scenario = ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55)

            # _fake_llm_client 的供应商每轮 delay_change=1.0 > 0.5，连续两轮触发原材料断供
            first_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            first_engine.set_round_callback(
                lambda state, messages: first_engine.abort() if state.round == 1 else None
            )
            first_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=3,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
            )
            first_engine.run()

            checkpoint = checkpoint_repo.latest_for_project(project.id)
            # 第 1 轮供应商已延迟一次，计数 1 随检查点保存
            self.assertEqual(checkpoint.engine_state["detector"]["supplier_delay_count"], 1)

            second_engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
            second_engine.configure(
                make_always_active_agents(),
                scenario,
                max_rounds=3,
                project_id=project.id,
                simulation_record=simulation_record,
                round_repository=round_repo,
                checkpoint_repository=checkpoint_repo,
                resume_checkpoint=checkpoint,
            )
            rounds = second_engine.run()

            # 恢复后第 2 轮再次延迟，连续计数达 2 → 触发原材料断供
            self.assertTrue(any("断供" in event.description for event in rounds[2].key_events))
            db.close()

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
            make_always_active_agents(),
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
            make_always_active_agents(),
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
            make_always_active_agents(),
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
                make_always_active_agents(),
                ScenarioParser.parse("Demo", "电子制造", "供应链压力 原材料 交付", initial_inventory=75, baseline_cost=55),
                max_rounds=1,
                project_id=project.id,
                knowledge_repository=KnowledgeRepository(db),
            )
            engine.run()

            # 检索命中后，知识块原文应出现在 user message 的 knowledge_context 段
            self.assertTrue(any("华东港口" in u for u in seen_users))
            db.close()

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
            make_always_active_agents(),
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

    def test_observation_collapses_repeated_actions(self) -> None:
        """观察层：同一行为体相邻轮次内容高度相似时折叠旧条目为「持续中」。"""
        engine = SimulationEngine(llm_client=make_fake_llm_client(), random_seed=1)
        agents = make_always_active_agents()
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
            make_always_active_agents(),
            ScenarioParser.parse("Demo", "电子制造", "供应链压力", initial_inventory=75, baseline_cost=55),
            max_rounds=1,
        )
        with mock.patch.object(app_config.llm, "decision_temperature", 0.5):
            engine.run()

        self.assertTrue(seen_options)
        self.assertTrue(all(o["temperature"] == 0.5 for o in seen_options))

    def test_process_page_heal_stale_status(self) -> None:
        """验证陈旧 running 状态的治愈判据：有检查点=中断，有数据=完成，否则草稿。"""
        from ui.process_page import ProcessPage  # 局部导入，避免 UI 依赖拖累其他用例

        heal = ProcessPage._heal_stale_status
        self.assertEqual(heal(has_checkpoint=True, has_data=True), "interrupted")
        self.assertEqual(heal(has_checkpoint=True, has_data=False), "interrupted")
        self.assertEqual(heal(has_checkpoint=False, has_data=True), "completed")
        self.assertEqual(heal(has_checkpoint=False, has_data=False), "draft")


if __name__ == "__main__":
    unittest.main()
