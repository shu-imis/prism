"""Agent 工厂

从 8 个固定模板生成 Agent 实例。
Day 1 版：直接从模板实例化。
后续迭代：支持 LLM 动态修饰 profile（参考 MiroFish OasisProfileGenerator）。
"""
from __future__ import annotations

from typing import List
from prism.core.agent import Agent, AGENT_TEMPLATES


class AgentFactory:
    """Agent 工厂 —— 从预定义模板创建 Agent 实例"""

    @staticmethod
    def create_all() -> List[Agent]:
        """创建全部 8 个 Agent"""
        agents: List[Agent] = []
        for tmpl in AGENT_TEMPLATES:
            agent = Agent(
                id=tmpl["id"],
                name=tmpl["name"],
                role=tmpl["role"],
                stance=tmpl["stance"],
                base_stance=tmpl["stance"],
                influence=tmpl["influence"],
                activity=tmpl["activity"],
                active_hours=tmpl["active_hours"],
                profile=tmpl["profile"],
            )
            agents.append(agent)
        return agents

    @staticmethod
    def create_by_ids(agent_ids: List[int]) -> List[Agent]:
        """按 ID 创建指定 Agent"""
        agents = []
        for tmpl in AGENT_TEMPLATES:
            if tmpl["id"] in agent_ids:
                agent = Agent(
                    id=tmpl["id"],
                    name=tmpl["name"],
                    role=tmpl["role"],
                    stance=tmpl["stance"],
                    base_stance=tmpl["stance"],
                    influence=tmpl["influence"],
                    activity=tmpl["activity"],
                    active_hours=tmpl["active_hours"],
                    profile=tmpl["profile"],
                )
                agents.append(agent)
        return agents

    @staticmethod
    def get_template(agent_id: int) -> dict | None:
        """获取指定 ID 的 Agent 模板"""
        for tmpl in AGENT_TEMPLATES:
            if tmpl["id"] == agent_id:
                return tmpl
        return None
