"""AI 动作服务：三个业务入口与统一的客户端准备。

页面通过本模块发起 AI 动作，不直触 LLM 客户端构造与分析函数。
"""
from __future__ import annotations

from typing import Any

from core.world_state import WorldState
from llm import analysis
from llm.client import LLMClient
from llm.config import build_llm_client
from report.generator import SimulationReport

# 未配置可用 Key 时的统一提示；页面按自身方式展示
CLIENT_UNAVAILABLE_MESSAGE = "未找到可用的 LLM 配置，请到左侧「设置」页填写 API Key"


def prepare_client() -> LLMClient | None:
    """构造 LLM 客户端；未配置可用 Key 时返回 None。"""
    return build_llm_client()


def extract_scenario(client: LLMClient, docs_text: str) -> dict[str, Any]:
    """文档文本 → 场景配置（Step1 自动填写）。"""
    return analysis.extract_scenario_from_docs(client, docs_text)


def generate_persona(client: LLMClient, scenario: dict[str, Any]) -> dict[str, Any]:
    """场景 → 行为体性格与种子事件（Step2 生成）。"""
    return analysis.generate_agent_config(client, scenario)


def analyze_evolution(
    client: LLMClient, report: SimulationReport, rounds: list[WorldState]
) -> dict[str, Any]:
    """仿真结果 → 叙述式综合分析（Step4 生成）。"""
    return analysis.analyze_evolution(client, report, rounds)
