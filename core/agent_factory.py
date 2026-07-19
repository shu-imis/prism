"""Agent 工厂

从 7 个固定模板生成供应链行为体实例。
"""
from __future__ import annotations

from core.agent import Agent, AGENT_TEMPLATES


class AgentFactory:
    """Agent 工厂 —— 从预定义模板创建行为体实例"""

    @staticmethod
    def create_all() -> list[Agent]:
        """创建全部 7 个行为体"""
        agents: list[Agent] = []
        for tmpl in AGENT_TEMPLATES:
            agent = Agent(
                id=tmpl["id"],
                name=tmpl["name"],
                role=tmpl["role"],
                decision_stance=tmpl["decision_stance"],
                base_stance=tmpl["decision_stance"],
                influence=tmpl["influence"],
                activity=tmpl["activity"],
                active_cycles=tmpl["active_cycles"],
                profile=tmpl["profile"],
            )
            agents.append(agent)
        return agents

    @staticmethod
    def create_by_ids(agent_ids: list[int]) -> list[Agent]:
        """按 ID 创建指定行为体"""
        agents = []
        for tmpl in AGENT_TEMPLATES:
            if tmpl["id"] in agent_ids:
                agent = Agent(
                    id=tmpl["id"],
                    name=tmpl["name"],
                    role=tmpl["role"],
                    decision_stance=tmpl["decision_stance"],
                    base_stance=tmpl["decision_stance"],
                    influence=tmpl["influence"],
                    activity=tmpl["activity"],
                    active_cycles=tmpl["active_cycles"],
                    profile=tmpl["profile"],
                )
                agents.append(agent)
        return agents

    @staticmethod
    def apply_overrides(agents: list[Agent], agents_config: dict | None) -> list[Agent]:
        """按行为体 id 应用性格覆盖（stance/activity/influence/profile），返回 agents。"""
        if not agents_config:
            return agents
        for agent in agents:
            config = agents_config.get(str(agent.id))
            if not config:
                continue
            if "stance" in config:
                agent.decision_stance = config["stance"]
                agent.base_stance = config["stance"]
            if "activity" in config:
                agent.activity = config["activity"]
            if "influence" in config:
                agent.influence = config["influence"]
            if "profile" in config:
                agent.profile = config["profile"]
        return agents

    @staticmethod
    def get_template(agent_id: int) -> dict | None:
        """获取指定 ID 的行为体模板"""
        for tmpl in AGENT_TEMPLATES:
            if tmpl["id"] == agent_id:
                return tmpl
        return None
