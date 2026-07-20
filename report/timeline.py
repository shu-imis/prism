"""演化时间线构建。

把逐轮行为体行动聚合为持续片段，并与关键事件按周期交织排序。
供结果页（Qt 渲染）与报告导出（Markdown 渲染）共用。
"""
from __future__ import annotations

from core.agent import AGENT_TEMPLATES
from core.world_state import WorldState

AGENT_NAMES = {tmpl["id"]: tmpl["name"] for tmpl in AGENT_TEMPLATES}


def build_action_episodes(rounds: list[WorldState]) -> list[dict]:
    """把逐轮行为体行动聚合为持续片段：同一行为体连续相同行动合并。"""
    episodes = []
    open_eps = {}

    def close(agent_id):
        episode = open_eps.pop(agent_id, None)
        if episode:
            episodes.append(episode)

    for state in rounds:
        for agent_id in list(open_eps):
            if agent_id not in state.agent_states:
                close(agent_id)
        for agent_id, snapshot in state.agent_states.items():
            summary = snapshot.decision_summary or snapshot.speech
            if not snapshot.spoke or not summary:
                close(agent_id)
                continue
            key = (summary, snapshot.action_type, snapshot.reaction_to)
            episode = open_eps.get(agent_id)
            if episode and episode["key"] == key:
                episode["end"] = state.round
            else:
                close(agent_id)
                open_eps[agent_id] = {
                    "key": key,
                    "agent_id": agent_id,
                    "summary": summary,
                    "action_type": snapshot.action_type,
                    "reaction_to": snapshot.reaction_to,
                    "start": state.round,
                    "end": state.round,
                }
    for agent_id in list(open_eps):
        close(agent_id)
    return episodes


def build_timeline_entries(rounds: list[WorldState]) -> list[dict]:
    """关键事件与行为体行动片段按周期交织排序（事件先于同周期行动）。"""
    entries = []
    for state in rounds:
        for event in state.key_events:
            entries.append({
                "kind": "event",
                "round": state.round,
                "description": event.description,
            })
    for episode in build_action_episodes(rounds):
        entries.append({
            "kind": "episode",
            "round": episode["start"],
            **episode,
        })
    entries.sort(key=lambda item: (item["round"], 0 if item["kind"] == "event" else 1))
    return entries


def format_rounds_span(start: int, end: int) -> str:
    """周期区间文案：单周期为「周期 N」，跨周期为「周期 N-M」。"""
    return f"周期 {start}" if start == end else f"周期 {start}-{end}"
