from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.action_feed import ActionFeed, ActionRecord
from core.agent_factory import AgentFactory
from core.document_importer import chunk_text, import_documents, render_imported_documents
from core.events import EventDetector
from core.scenario_parser import ScenarioParser
from core.simulation_engine import SimulationEngine
from core.world_state import KeyEvent, WorldState
from llm.client import LLMClient, LLMProvider, ProviderSettings
from tests.helpers import make_always_active_agents


class CoreModuleTests(unittest.TestCase):
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

    def test_event_detector_state_round_trip(self) -> None:
        """验证 EventDetector 连续计数的序列化/恢复（缺省字段兼容旧检查点）。"""
        detector = EventDetector()
        detector.detect(WorldState(round=1, simulated_hour=1), supplier_delayed=True)
        restored = EventDetector.from_dict(detector.to_dict())
        # 续传的计数再累计一次即触发原材料断供
        events = restored.detect(WorldState(round=2, simulated_hour=2), supplier_delayed=True)
        self.assertTrue(any("断供" in event.description for event in events))

        # 旧格式检查点没有 detector 键：缺省计数为 0，单次延迟不触发
        fresh = EventDetector.from_dict({})
        events = fresh.detect(WorldState(round=1, simulated_hour=1), supplier_delayed=True)
        self.assertEqual(events, [])

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
            make_always_active_agents(),
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


if __name__ == "__main__":
    unittest.main()
