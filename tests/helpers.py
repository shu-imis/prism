"""测试共享助手：fake LLM transport、行为体工厂、内存 keyring。"""
from __future__ import annotations

import time

from core.agent_factory import AgentFactory
from llm.client import LLMClient, LLMProvider, ProviderSettings


def make_fake_llm_client(slow_supplier_seconds: float = 0.0) -> LLMClient:
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
            # 超时测试用：让供应商 LLM 调用睡眠，其余行为体即时返回
            if slow_supplier_seconds:
                time.sleep(slow_supplier_seconds)
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


def make_always_active_agents():
    agents = AgentFactory.create_all()
    for agent in agents:
        agent.activity = 1.0
        agent.active_cycles = list(range(1, 13))
    return agents


def make_json_client(payload: str) -> LLMClient:
    return LLMClient(
        providers=[ProviderSettings(LLMProvider.OPENAI, "test-model", "key")],
        max_retries=0,
        transport=lambda provider, messages, options: payload,
    )


class FakeKeyring:
    """内存版 keyring，避免测试触碰真实系统钥匙串。"""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.store[(service, username)]
