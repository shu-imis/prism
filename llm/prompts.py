"""Prompt 模板管理

集中管理所有 LLM 交互的 Prompt 模板。
"""
from __future__ import annotations


# ============================================================
# 行为体响应 Prompt
# ============================================================

AGENT_RESPONSE_SYSTEM = """你正在参与一个供应链决策推演仿真。你是以下角色：

{agent_profile}

当前仿真状态：
- 周期：第 {cycle} 轮
- 全链库存水平：{inventory_level}/100
- 成本指数：{cost_index}/100
- 平均交付延迟：{delivery_delay} 周期
- 订单满足率：{service_level:.0%}
- 全链利润率：{profit_margin:+.1%}

你的当前状态：
- 压力水平：{pressure:.2f}（0=轻松，1=极度紧张）
- 产能利用率：{capacity:.0%}

最近发生的重大事件：
{recent_events}

你最近的记忆：
{memory}

请以你的角色身份，根据当前供应链状态做出决策响应。输出 JSON 格式：
{{
    "inventory_change": float,    // 库存变化（对你的节点，-20~20）
    "cost_change": float,         // 成本变化（对你的节点，-10~15）
    "delay_change": float,        // 交付延迟变化（-1~2 周期）
    "service_change": float,      // 服务水平变化（-0.1~0.1）
    "margin_change": float,       // 利润率变化（-0.08~0.08）
    "pressure_change": float,     // 自身压力变化（-0.2~0.2）
    "risk_description": "当前面临的主要风险描述",
    "response_summary": "你的决策响应摘要",
    "decision_shift": "none|toward_aggressive|toward_cautious|toward_cooperative|toward_defensive"
}}
"""


# ============================================================
# 策略评估 Prompt（预留：LLM 驱动的方案评估）
# ============================================================

STRATEGY_EVALUATION_SYSTEM = """你是一位供应链决策评估专家。请评估以下决策方案的仿真结果。

方案名称：{strategy_name}
方案决策：{strategy_decision}

仿真数据：
- 最终库存水平：{final_inventory}/100
- 最终成本指数：{final_cost}/100
- 最终交付延迟：{final_delay} 周期
- 最终服务水平：{final_service}
- 最终利润率：{final_margin}
- 触发关键事件数：{key_event_count}
- 关键事件列表：{key_events}

请从以下维度评 1-10 分并给出文字说明：
1. 成本控制
2. 交付稳定性
3. 库存健康度
4. 风险抵御
5. 协同效率
6. 可执行性

输出 JSON 格式：
{{
    "scores": {{"cost_control": 7, "delivery_stability": 6, "inventory_health": 8, "risk_resistance": 7, "collaboration_efficiency": 6, "executability": 8}},
    "summary": "总体评价文字",
    "recommendation": "建议文字",
    "risks": ["风险点1", "风险点2"]
}}
"""


# ============================================================
# 报告生成 Prompt（预留：LLM 驱动的报告生成）
# ============================================================

REPORT_GENERATION_SYSTEM = """你是一位专业的供应链决策分析师。请根据以下仿真数据生成评估报告。

供应链背景：
{scenario_background}

方案对比数据：
{strategies_data}

请生成结构化报告，包含：
1. 执行摘要
2. 方案对比分析
3. 风险评估
4. 建议

输出 JSON 格式：
{{
    "executive_summary": "执行摘要",
    "strategy_comparison": [
        {{"name": "方案名", "analysis": "分析文字", "score": 7.5}}
    ],
    "risk_assessment": [
        {{"risk": "风险描述", "severity": "high|medium|low", "mitigation": "缓解建议"}}
    ],
    "recommendations": ["建议1", "建议2"]
}}
"""
