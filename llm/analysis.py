"""AI 业务调用层。

全链路 AI 集成的三个业务入口：
- extract_scenario_from_docs：Step1 文档分析 → 场景配置
- generate_agent_config：Step2 场景 → 行为体性格与种子事件
- analyze_evolution：Step4 仿真结果 → 叙述式综合分析

纯 Python、无 Qt 依赖，便于测试；所有函数在 LLM 调用或校验失败时抛异常，
由调用方（UI worker）捕获并降级。
"""
from __future__ import annotations

import json
from typing import Any

from config import app_config
from core.agent import AGENT_TEMPLATES
from llm.client import LLMClient
from llm.prompts import (
    EVOLUTION_ANALYSIS_SYSTEM,
    PERSONA_GENERATION_SYSTEM,
    SCENARIO_EXTRACTION_SYSTEM,
)

# 传给 LLM 的文档全文上限
MAX_DOC_CHARS = 30000

# 与 ui/event_page.py NODE_TYPES 一致的合法节点类型
VALID_NODE_TYPES = {
    "supplier", "manufacturer", "distributor", "retailer",
    "logistics", "consumer", "regulator",
}

# 与 ui/persona_page.py STANCES 一致的合法决策倾向
VALID_STANCES = {"aggressive", "cautious", "cooperative", "defensive"}

MAX_NODES = 8
MAX_SEED_EVENTS = 3


def extract_scenario_from_docs(client: LLMClient, docs_text: str) -> dict[str, Any]:
    """从导入文档文本中抽取场景配置（Step1 自动填写）。"""
    text = (docs_text or "").strip()
    if not text:
        raise ValueError("没有可供分析的文档内容")
    data = client.chat_json(SCENARIO_EXTRACTION_SYSTEM, text[:MAX_DOC_CHARS])
    return _validate_scenario(data)


def generate_agent_config(client: LLMClient, scenario: dict[str, Any]) -> dict[str, Any]:
    """基于场景生成 7 个行为体的性格配置与种子事件（Step2）。"""
    scenario_brief = {
        "title": scenario.get("title", ""),
        "industry": scenario.get("industry", ""),
        "background": scenario.get("background", ""),
        "nodes": [
            {"name": n.get("name", ""), "type": n.get("type", "")}
            for n in scenario.get("nodes", [])
            if isinstance(n, dict)
        ],
    }
    agent_brief = [
        {
            "id": t["id"],
            "name": t["name"],
            "role": t["role"],
            "default_stance": t["decision_stance"],
        }
        for t in AGENT_TEMPLATES
    ]
    user = json.dumps(
        {"scenario": scenario_brief, "agents": agent_brief},
        ensure_ascii=False,
    )
    data = client.chat_json(PERSONA_GENERATION_SYSTEM, user)
    return _validate_agent_config(data)


def analyze_evolution(client: LLMClient, report, rounds: list) -> dict[str, Any]:
    """对仿真结果生成叙述式综合分析（Step4）。

    report 为 SimulationReport，rounds 为 WorldState 列表；失败抛异常，
    调用方降级为纯公式输出。
    """
    from report.timeline import build_timeline_entries  # 延迟导入避免环

    timeline = build_timeline_entries(rounds or [])
    timeline_lines = []
    for entry in timeline[:40]:
        if entry["kind"] == "event":
            timeline_lines.append(f"周期 {entry['round']} 事件：{entry['description']}")
        else:
            timeline_lines.append(
                f"周期 {entry['start']}-{entry['end']} 行为体{entry['agent_id']}"
                f"【{entry.get('action_type', '')}】：{entry.get('summary', '')}"
            )

    payload = {
        "project_name": report.project_name,
        "scenario_background": report.scenario_background,
        "metrics": {
            "inventory": {"first": report.final_inventory - report.inventory_delta, "final": report.final_inventory},
            "cost": {"first": report.final_cost - report.cost_delta, "final": report.final_cost},
            "delivery_delay": {"first": report.final_delivery_delay - report.delay_delta, "final": report.final_delivery_delay},
            "service_level": {"first": report.final_service_level - report.service_delta, "final": report.final_service_level},
            "profit_margin": {"first": report.final_profit_margin - report.margin_delta, "final": report.final_profit_margin},
        },
        "scores": report.scores,
        "detected_risks": report.risks,
        "key_events": report.key_events,
        "timeline": timeline_lines,
    }
    data = client.chat_json(EVOLUTION_ANALYSIS_SYSTEM, json.dumps(payload, ensure_ascii=False))
    return _validate_evolution_analysis(data)


# ============================================================
# 校验与归一化
# ============================================================

def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(float(value))))
    except (TypeError, ValueError):
        return default


def _clamp_float(value, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_scenario(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("场景抽取结果必须是 JSON 对象")

    nodes: list[dict[str, Any]] = []
    for raw in data.get("nodes", []):
        if len(nodes) >= MAX_NODES:
            break
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        node_type = raw.get("type")
        nodes.append({
            "name": name[:40],
            "type": node_type if node_type in VALID_NODE_TYPES else "supplier",
            "inventory": _clamp_int(raw.get("inventory"), 0, 100, 50),
            "lead_time": _clamp_int(raw.get("lead_time"), 0, 10, 2),
            "capacity": _clamp_int(raw.get("capacity"), 1, 200, 100),
            "cost_index": _clamp_int(raw.get("cost_index"), 0, 100, 50),
            "upstream": _str_list(raw.get("upstream")),
            "downstream": _str_list(raw.get("downstream")),
        })

    background = str(data.get("background", "")).strip()
    if not background:
        raise ValueError("AI 未能从文档中抽取出供应链背景")

    return {
        "title": str(data.get("title", "")).strip()[:80],
        "industry": str(data.get("industry", "")).strip()[:40],
        "background": background,
        "nodes": nodes,
        "initial_inventory": _clamp_int(data.get("initial_inventory"), 0, 100, 75),
        "baseline_cost": _clamp_int(data.get("baseline_cost"), 0, 100, 50),
        "baseline_service_level": _clamp_float(data.get("baseline_service_level"), 0.0, 1.0, 0.85),
    }


def _validate_agent_config(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("行为体配置结果必须是 JSON 对象")

    raw_config = data.get("agents_config", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    agents_config: dict[str, Any] = {}
    for tmpl in AGENT_TEMPLATES:
        cfg = raw_config.get(str(tmpl["id"]), {})
        if not isinstance(cfg, dict):
            cfg = {}
        stance = cfg.get("stance")
        profile = str(cfg.get("profile", "")).strip()
        agents_config[str(tmpl["id"])] = {
            "stance": stance if stance in VALID_STANCES else tmpl["decision_stance"],
            "activity": round(_clamp_float(cfg.get("activity"), 0.0, 1.0, tmpl["activity"]), 2),
            "influence": round(_clamp_float(cfg.get("influence"), 0.5, 3.0, tmpl["influence"]), 1),
            "profile": profile or tmpl["profile"],
        }

    max_cycle = max(app_config.sim.max_rounds, 1)
    seed_events: list[dict[str, Any]] = []
    for raw in data.get("seed_events", []):
        if len(seed_events) >= MAX_SEED_EVENTS:
            break
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content", "")).strip()
        if not content:
            continue
        seed_events.append({
            "content": content,
            "cycle": _clamp_int(raw.get("cycle"), 1, max_cycle, 1),
        })

    return {"agents_config": agents_config, "seed_events": seed_events}


def _validate_evolution_analysis(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("AI 分析结果必须是 JSON 对象")

    analysis = str(data.get("evolution_analysis", "")).strip()
    if not analysis:
        raise ValueError("AI 未返回演化分析内容")

    recommendations = [
        str(item).strip()
        for item in data.get("recommendations", [])
        if str(item).strip()
    ][:5] if isinstance(data.get("recommendations"), list) else []

    return {
        "evolution_analysis": analysis,
        "risk_analysis": str(data.get("risk_analysis", "")).strip(),
        "recommendations": recommendations,
    }
