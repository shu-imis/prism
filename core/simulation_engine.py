"""仿真引擎 —— 真实 LLM 多行为体主循环。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Any, Callable, Optional

from config import app_config
from core.action_feed import ActionFeed, ActionRecord
from core.agent import Agent
from core.events import EventDetector
from core.scenario_parser import Scenario
from core.world_state import AgentSnapshot, NodeState, WorldState
from core import clamp, clamp_float
from db.models import Checkpoint, CheckpointRepository, KnowledgeRepository, SimulationRoundRepository
from llm.client import LLMClient
from llm.prompts import AGENT_RESPONSE_SYSTEM

AGENT_NODE_TYPES: dict[int, tuple[str, ...]] = {
    1: ("supplier",),
    2: ("manufacturer",),
    3: ("distributor",),
    4: ("retailer",),
    5: ("logistics",),
    6: ("consumer",),
    7: ("regulator",),
}

VALID_DECISION_SHIFTS = {
    "none",
    "toward_aggressive",
    "toward_cautious",
    "toward_cooperative",
    "toward_defensive",
}

# 行为体行动空间（MiroFish/OASIS 式受限动作）：LLM 每轮必须从中选择行动类型
ACTION_TYPES = {
    "maintain",            # 维持现状
    "adjust_supply",       # 调整供应/采购量
    "adjust_price",        # 调价/促销
    "adjust_capacity",     # 产能/库存策略调整
    "expedite_logistics",  # 物流加急/改道
    "reduce_orders",       # 削减订单
    "shift_demand",        # 需求转移/抵制
    "intervene",           # 监管介入
}

# 各行为体允许的行动子集；越权或非法值降级为 maintain
AGENT_ALLOWED_ACTIONS: dict[int, set[str]] = {
    1: {"maintain", "adjust_supply", "adjust_price", "reduce_orders"},
    2: {"maintain", "adjust_supply", "adjust_capacity", "reduce_orders", "expedite_logistics"},
    3: {"maintain", "adjust_supply", "adjust_capacity", "reduce_orders"},
    4: {"maintain", "adjust_price", "adjust_supply", "reduce_orders"},
    5: {"maintain", "expedite_logistics", "adjust_capacity"},
    6: {"maintain", "shift_demand", "reduce_orders"},
    7: {"maintain", "intervene"},
}

# 场景未定义节点链路时的类型级兜底链（与 AGENT_NODE_TYPES 主链一致）
_FALLBACK_TYPE_CHAIN = ("supplier", "manufacturer", "distributor", "retailer", "consumer")


class SimStatus(str, Enum):
    """仿真运行状态。"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class SimulationConfig:
    """单次仿真的运行配置。"""

    max_rounds: int = 12
    seed_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulationState:
    """仿真运行时状态。"""

    config: SimulationConfig = field(default_factory=SimulationConfig)
    status: SimStatus = SimStatus.IDLE
    current_round: int = 0
    total_rounds: int = 0
    agents: list[Agent] = field(default_factory=list)
    scenario: Optional[Scenario] = None
    error_message: str = ""
    project_id: int | None = None
    simulation_record: Any = None
    round_repository: SimulationRoundRepository | None = None
    checkpoint_repository: CheckpointRepository | None = None
    knowledge_repository: KnowledgeRepository | None = None
    resume_checkpoint: Checkpoint | None = None
    round_timeout: int = 120


@dataclass
class AgentTurn:
    """单个行为体在一轮中的 LLM 输出。"""

    agent_id: int
    agent_name: str
    role: str
    decision_stance: str
    speech: str
    inventory_change: float = 0.0
    cost_change: float = 0.0
    delay_change: float = 0.0
    service_change: float = 0.0
    margin_change: float = 0.0
    pressure_change: float = 0.0
    decision_shift: str = "none"
    risk_description: str = ""
    response_summary: str = ""
    action_type: str = "maintain"
    reaction_to: str = "none"
    skipped: bool = False
    error_message: str = ""
    warning: str = ""

    def to_message(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "stance": self.decision_stance,
            "role": self.role,
            "decision_stance": self.decision_stance,
            "content": self.speech,
            "action_type": self.action_type,
            "reaction_to": self.reaction_to,
            "metrics": {
                "inventory_change": self.inventory_change,
                "cost_change": self.cost_change,
                "delay_change": self.delay_change,
                "service_change": self.service_change,
                "margin_change": self.margin_change,
                "pressure_change": self.pressure_change,
                "decision_shift": self.decision_shift,
                "risk_description": self.risk_description,
                "response_summary": self.response_summary,
                "skipped": self.skipped,
                "error_message": self.error_message,
                "warning": self.warning,
            },
        }


RoundCallback = Callable[[WorldState, list[dict[str, Any]]], None]


class SimulationRecoverableError(RuntimeError):
    """仿真已保存检查点，可修复配置后恢复。"""


class SimulationEngine:
    """管理单一世界、多轮、多行为体的真实 LLM 推演生命周期。"""

    def __init__(self, llm_client: LLMClient | None = None, random_seed: int = 42):
        self.state = SimulationState()
        self.llm_client = llm_client
        self.random_seed = random_seed
        self._rng = random.Random(random_seed)
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None
        self._round_callback: RoundCallback | None = None
        self._resume_payload: dict[str, Any] | None = None

    def configure(
        self,
        agents: list[Agent],
        scenario: Scenario,
        *,
        seed_events: list[dict[str, Any]] | None = None,
        max_rounds: int | None = None,
        project_id: int | None = None,
        simulation_record: Any = None,
        round_repository: SimulationRoundRepository | None = None,
        checkpoint_repository: CheckpointRepository | None = None,
        knowledge_repository: KnowledgeRepository | None = None,
        resume_checkpoint: Checkpoint | None = None,
        round_timeout: int | None = None,
    ) -> None:
        """配置仿真参数。"""

        self.state.config = SimulationConfig(
            max_rounds=max_rounds or app_config.sim.max_rounds,
            seed_events=list(seed_events or []),
        )
        self.state.agents = agents
        self.state.scenario = scenario
        self.state.total_rounds = self.state.config.max_rounds
        self.state.status = SimStatus.IDLE
        self.state.project_id = project_id
        self.state.simulation_record = simulation_record
        self.state.round_repository = round_repository
        self.state.checkpoint_repository = checkpoint_repository
        self.state.knowledge_repository = knowledge_repository
        self.state.resume_checkpoint = resume_checkpoint
        self.state.round_timeout = round_timeout or app_config.sim.round_timeout
        self._resume_payload = resume_checkpoint.engine_state if resume_checkpoint else None
        self._rng = random.Random(self.random_seed)

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """设置进度回调 —— 用于 UI 更新。"""
        self._progress_callback = callback

    def set_round_callback(self, callback: RoundCallback) -> None:
        """设置轮次回调 —— 用于 UI 展示每轮状态和行为体响应。"""
        self._round_callback = callback

    def run(self) -> list[WorldState]:
        """运行完整仿真（同步模式，UI 应放在线程中调用）。"""

        if not self.state.agents:
            raise ValueError("至少需要配置一个行为体。")

        self.state.status = SimStatus.RUNNING

        try:
            rounds = self._run_simulation()
            if self.state.status != SimStatus.ABORTED:
                self.state.status = SimStatus.COMPLETED
                self._delete_checkpoints()

        except Exception as exc:
            self.state.status = SimStatus.ERROR
            self.state.error_message = str(exc)
            raise

        return rounds

    def _run_simulation(self) -> list[WorldState]:
        max_rounds = self.state.config.max_rounds
        detector = EventDetector()
        resume = self._resume_payload
        if resume:
            agents = [Agent.from_dict(item) for item in resume.get("agents", [])]
            rounds = [WorldState.from_dict(item) for item in resume.get("current_rounds", [])]
            start_round = int(resume.get("last_round", 0)) + 1
            ws = rounds[-1] if rounds else self._initial_world_state(agents)
        else:
            agents = self._clone_agents()
            rounds = [self._initial_world_state(agents)]
            ws = rounds[0]
            start_round = 1
            self._persist_round(ws, [])
            self._save_checkpoint(ws, agents, rounds)

        # 行动信息流：行为体互动的共享载体。检查点恢复时从空开始，
        # 首轮观察降级为"暂无"，随后续轮次逐轮重建（不改变 checkpoint schema）
        feed = ActionFeed()

        for round_index in range(start_round, max_rounds + 1):
            self._wait_if_paused()
            if self.state.status == SimStatus.ABORTED:
                self._save_checkpoint(ws, agents, rounds)
                break

            round_started = time.monotonic()
            self._inject_seed_events(feed, round_index)
            active_agents = self._select_active_agents(agents, round_index)

            turns: list[AgentTurn] = []
            for agent in active_agents:
                self._wait_if_paused()
                if self.state.status == SimStatus.ABORTED:
                    break
                if time.monotonic() - round_started > self.state.round_timeout:
                    turns.append(self._skipped_turn(agent, "本轮超过最大耗时，已跳过剩余行为体。", warning="round_timeout"))
                    continue
                try:
                    turn = self._generate_agent_turn(agent, ws, feed=feed, agents=agents)
                    self._apply_agent_turn(agent, turn)
                except Exception as exc:  # noqa: BLE001 - LLM SDK 错误类型不统一
                    turn = self._skipped_turn(agent, str(exc))
                turns.append(turn)

            # 事件检测参数推导
            supplier_delayed = any(
                self._agent_has_node_type(self._agent_by_id(agents, turn.agent_id), "supplier")
                and turn.delay_change > 0.5
                and not turn.skipped
                for turn in turns
            )
            retailer_margin_negative = any(
                self._agent_has_node_type(self._agent_by_id(agents, turn.agent_id), "retailer")
                and turn.margin_change < 0
                and not turn.skipped
                for turn in turns
            )
            regulator_risk_flagged = any(
                self._agent_has_node_type(self._agent_by_id(agents, turn.agent_id), "regulator")
                and "风险" in turn.risk_description
                and not turn.skipped
                for turn in turns
            )
            demand_surge_detected = any(
                self._agent_has_node_type(self._agent_by_id(agents, turn.agent_id), "consumer")
                and turn.inventory_change < -8
                and not turn.skipped
                for turn in turns
            )

            next_state = self._build_next_state(
                previous=ws,
                agents=agents,
                turns=turns,
                round_index=round_index,
                cycle=round_index,
            )
            events = detector.detect(
                next_state,
                supplier_delayed=supplier_delayed,
                retailer_margin_negative=retailer_margin_negative,
                regulator_risk_flagged=regulator_risk_flagged,
                demand_surge_detected=demand_surge_detected,
            )
            self._apply_events(next_state, agents, events)
            self._apply_bullwhip_effect(agents)

            # 本轮行动写入共享信息流，供后续轮次的行为体观察（同步更新语义：
            # 同轮行为体互不可见，反应链跨轮形成，与 MiroFish/OASIS 一致）
            feed.append(
                ActionRecord(
                    round=round_index,
                    agent_id=turn.agent_id,
                    agent_name=turn.agent_name,
                    role=turn.role,
                    action_type=turn.action_type,
                    content=turn.response_summary,
                    metrics={
                        "inventory_change": turn.inventory_change,
                        "cost_change": turn.cost_change,
                        "delay_change": turn.delay_change,
                        "service_change": turn.service_change,
                        "margin_change": turn.margin_change,
                    },
                    influence=self._agent_by_id(agents, turn.agent_id).influence,
                    reaction_to=turn.reaction_to,
                )
                for turn in turns
                if not turn.skipped and turn.response_summary
            )

            rounds.append(next_state)
            ws = next_state
            messages = [turn.to_message() for turn in turns]

            # 校验 AI 参与度，防止空转
            all_skipped = active_agents and all(turn.skipped for turn in turns)

            if all_skipped:
                if round_index == 1:
                    raise RuntimeError(
                        "首轮所有行为体均调用失败，请检查 LLM API Key 是否已配置"
                    )
                raise SimulationRecoverableError(
                    f"第 {round_index} 轮所有激活行为体均调用失败或超时，已保存检查点"
                )

            self._persist_round(ws, messages)
            self._save_checkpoint(ws, agents, rounds)
            self._emit_callbacks(ws, messages)

        return rounds

    def _inject_seed_events(self, feed: ActionFeed, cycle: int) -> None:
        """注入种子事件 —— MiroFish initial_posts 式的世界干预。

        在当轮行为体行动前写入共享信息流，当轮即可被观察；
        influence=2.5 超过全链广播阈值，保证非邻居行为体同样可见。
        """
        for event in self.state.config.seed_events:
            content = str(event.get("content", "")).strip()
            try:
                event_cycle = int(event.get("cycle", 1))
            except (TypeError, ValueError):
                continue
            if event_cycle != cycle or not content:
                continue
            feed.append(
                [
                    ActionRecord(
                        round=cycle,
                        agent_id=0,
                        agent_name="世界事件",
                        role=str(event.get("actor", "") or "外部干预"),
                        action_type="seed",
                        content=content,
                        influence=2.5,
                    )
                ]
            )

    def _ensure_llm_client(self) -> LLMClient:
        if self.llm_client is None:
            self.llm_client = LLMClient.from_env()
        return self.llm_client

    def _initial_world_state(self, agents: list[Agent]) -> WorldState:
        scenario = self.state.scenario
        node_states = self._initial_node_states()
        inventory_level, cost_index, delivery_delay, service_level, profit_margin, resilience_score = (
            self._aggregate_node_metrics(node_states)
            if node_states
            else (
                scenario.initial_inventory if scenario else 75.0,
                scenario.baseline_cost if scenario else 50.0,
                0.0,
                scenario.baseline_service_level if scenario else 0.85,
                0.15,
                60.0,
            )
        )
        return WorldState(
            round=0,
            simulated_hour=0,
            inventory_level=inventory_level,
            cost_index=cost_index,
            delivery_delay=delivery_delay,
            service_level=service_level,
            profit_margin=profit_margin,
            resilience_score=resilience_score,
            agent_states=self._snapshot_all(agents),
            node_states=node_states,
        )

    def _save_checkpoint(
        self,
        state: WorldState,
        agents: list[Agent],
        current_rounds: list[WorldState],
    ) -> None:
        repo = self.state.checkpoint_repository
        project_id = self.state.project_id
        simulation_id = self._simulation_record_id()
        if not repo or project_id is None or simulation_id is None:
            return
        engine_state = {
            "last_round": state.round,
            "agents": [agent.to_dict() for agent in agents],
            "current_rounds": [round_state.to_dict() for round_state in current_rounds],
            "scenario": self.state.scenario.to_dict() if self.state.scenario else {},
            "seed_events": self.state.config.seed_events,
            "max_rounds": self.state.config.max_rounds,
        }
        repo.save(
            project_id=project_id,
            simulation_id=simulation_id,
            last_round=state.round,
            engine_state=engine_state,
        )

    def _delete_checkpoints(self) -> None:
        if self.state.checkpoint_repository and self.state.project_id is not None:
            self.state.checkpoint_repository.delete_for_project(self.state.project_id)

    def _wait_if_paused(self) -> None:
        while self.state.status == SimStatus.PAUSED:
            time.sleep(0.2)

    @staticmethod
    def _skipped_turn(agent: Agent, error_message: str, warning: str = "") -> AgentTurn:
        return AgentTurn(
            agent_id=agent.id,
            agent_name=agent.name,
            role=agent.role,
            decision_stance=agent.decision_stance,
            speech="",
            skipped=True,
            error_message=error_message,
            warning=warning,
        )

    def _generate_agent_turn(
        self,
        agent: Agent,
        state: WorldState,
        feed: ActionFeed,
        agents: list[Agent],
    ) -> AgentTurn:
        scenario = self.state.scenario or Scenario()
        observation = self._build_observation(agent, agents, feed, state)
        system_prompt = AGENT_RESPONSE_SYSTEM.format(
            agent_profile=agent.profile,
            cycle=state.simulated_hour,
            inventory_level=state.inventory_level,
            cost_index=state.cost_index,
            delivery_delay=state.delivery_delay,
            service_level=state.service_level,
            profit_margin=state.profit_margin,
            pressure=agent.pressure,
            capacity=agent.capacity,
            recent_events=self._format_recent_events(state),
            observation=observation,
        )
        user_message = "\n".join(
            [
                f"supply_chain={scenario.title}",
                f"industry={scenario.industry}",
                f"background={scenario.background}",
                "current_metrics:",
                self._format_current_metrics(state),
                "all_nodes:",
                self._format_nodes_summary(state=state),
                "relevant_nodes:",
                self._format_nodes_summary(state=state, agent=agent, relevant_only=True),
                "knowledge_context:",
                self._retrieve_knowledge_context(agent, state),
                "Return JSON only.",
            ]
        )
        data = self._ensure_llm_client().chat_json(system_prompt, user_message, temperature=0.35)
        required_fields = {
            "inventory_change",
            "cost_change",
            "delay_change",
            "service_change",
            "margin_change",
            "pressure_change",
            "risk_description",
            "response_summary",
            "decision_shift",
        }
        missing = sorted(field for field in required_fields if field not in data)
        if missing:
            raise ValueError(f"LLM 返回缺少必需字段：{', '.join(missing)}")
        decision_shift = str(data.get("decision_shift", "none"))
        if decision_shift not in VALID_DECISION_SHIFTS:
            raise ValueError(f"不支持的 decision_shift：{decision_shift}")
        action_type = str(data.get("action_type", "maintain")).strip() or "maintain"
        allowed_actions = AGENT_ALLOWED_ACTIONS.get(agent.id, ACTION_TYPES)
        warning = ""
        if action_type not in ACTION_TYPES or action_type not in allowed_actions:
            warning = f"action_type={action_type} 非法或超出角色行动空间，已降级为 maintain"
            action_type = "maintain"
        reaction_to = str(data.get("reaction_to", "none")).strip() or "none"
        return AgentTurn(
            agent_id=agent.id,
            agent_name=agent.name,
            role=agent.role,
            decision_stance=agent.decision_stance,
            speech=str(data.get("response_summary", "")).strip(),
            inventory_change=clamp_float(data.get("inventory_change", 0.0), -20.0, 20.0),
            cost_change=clamp_float(data.get("cost_change", 0.0), -10.0, 15.0),
            delay_change=clamp_float(data.get("delay_change", 0.0), -1.0, 2.0),
            service_change=clamp_float(data.get("service_change", 0.0), -0.1, 0.1),
            margin_change=clamp_float(data.get("margin_change", 0.0), -0.08, 0.08),
            pressure_change=clamp_float(data.get("pressure_change", 0.0), -0.2, 0.2),
            decision_shift=decision_shift,
            risk_description=str(data.get("risk_description", "")).strip(),
            response_summary=str(data.get("response_summary", "")).strip(),
            action_type=action_type,
            reaction_to=reaction_to,
            warning=warning,
        )

    def _build_next_state(
        self,
        *,
        previous: WorldState,
        agents: list[Agent],
        turns: list[AgentTurn],
        round_index: int,
        cycle: int,
    ) -> WorldState:
        # 按影响力权重聚合各行为体的指标变化
        weighted_inventory = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.inventory_change
            for turn in turns
            if not turn.skipped
        )
        weighted_cost = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.cost_change
            for turn in turns
            if not turn.skipped
        )
        weighted_delay = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.delay_change
            for turn in turns
            if not turn.skipped
        )
        weighted_service = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.service_change
            for turn in turns
            if not turn.skipped
        )
        weighted_margin = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.margin_change
            for turn in turns
            if not turn.skipped
        )

        total_influence = sum(
            self._agent_by_id(agents, turn.agent_id).influence
            for turn in turns
            if not turn.skipped
        ) or 1.0

        node_states = self._build_node_states(previous, agents, turns)
        if node_states:
            inventory_level, cost_index, delivery_delay, service_level, profit_margin, resilience_score = (
                self._aggregate_node_metrics(node_states)
            )
        else:
            quiet_recovery = 1.0 if not turns else 0.0
            inventory_level = clamp(previous.inventory_level + weighted_inventory / total_influence + quiet_recovery, 0.0, 100.0)
            cost_index = clamp(previous.cost_index + weighted_cost / total_influence, 0.0, 100.0)
            delivery_delay = max(0.0, previous.delivery_delay + weighted_delay / total_influence)
            service_level = clamp(previous.service_level + weighted_service / total_influence, 0.0, 1.0)
            profit_margin = clamp(previous.profit_margin + weighted_margin / total_influence, -1.0, 1.0)
            resilience_score = clamp(
                60.0 - (cost_index - 50) * 0.3 - delivery_delay * 5 + service_level * 20 + profit_margin * 30,
                0.0,
                100.0,
            )

        snapshots = self._snapshot_all(agents)
        for turn in turns:
            agent = self._agent_by_id(agents, turn.agent_id)
            snapshots[agent.id] = AgentSnapshot(
                agent_id=agent.id,
                pressure=agent.pressure,
                decision_stance=agent.decision_stance,
                spoke=not turn.skipped,
                speech=turn.speech if not turn.skipped else f"跳过：{turn.error_message[:120]}",
                decision_summary=turn.response_summary if not turn.skipped else "",
                action_type=turn.action_type if not turn.skipped else "",
                reaction_to=turn.reaction_to if not turn.skipped else "",
            )

        return WorldState(
            round=round_index,
            simulated_hour=cycle,
            inventory_level=inventory_level,
            cost_index=cost_index,
            delivery_delay=delivery_delay,
            service_level=service_level,
            profit_margin=profit_margin,
            resilience_score=resilience_score,
            agent_states=snapshots,
            node_states=node_states,
        )

    def _apply_events(self, state: WorldState, agents: list[Agent], events: list[Any]) -> None:
        state.key_events = events
        if state.node_states:
            self._apply_events_to_node_states(state.node_states, events)
            (
                state.inventory_level,
                state.cost_index,
                state.delivery_delay,
                state.service_level,
                state.profit_margin,
                state.resilience_score,
            ) = self._aggregate_node_metrics(state.node_states)
            return
        for event in events:
            state.inventory_level = clamp(state.inventory_level + event.inventory_delta, 0.0, 100.0)
            state.cost_index = clamp(state.cost_index + event.cost_delta, 0.0, 100.0)
            state.delivery_delay = max(0.0, state.delivery_delay + event.delay_delta)
            state.service_level = clamp(state.service_level + event.service_delta, 0.0, 1.0)
            state.profit_margin = clamp(state.profit_margin + event.margin_delta, -1.0, 1.0)

    def _apply_agent_turn(self, agent: Agent, turn: AgentTurn) -> None:
        if turn.skipped:
            return
        agent.pressure = clamp(agent.pressure + turn.pressure_change, 0.0, 1.0)
        agent.capacity = clamp(agent.capacity + turn.inventory_change * 0.005, 0.3, 1.5)
        if turn.decision_shift in VALID_DECISION_SHIFTS and turn.decision_shift != "none":
            agent.decision_stance = turn.decision_shift.replace("toward_", "")

    def _select_active_agents(self, agents: list[Agent], cycle: int) -> list[Agent]:
        """根据活跃周期与激活概率选择本轮参与的行为体。"""
        candidates = [
            agent for agent in agents
            if cycle in set(agent.active_cycles or range(1, 13))
        ]
        active: list[Agent] = []
        for agent in candidates:
            if self._rng.random() <= agent.activity:
                active.append(agent)
        # 保底：至少激活一个行为体，避免整轮空转
        if not active and candidates:
            active = [max(candidates, key=lambda a: a.influence)]
        return active

    def _build_observation(self, agent: Agent, agents: list[Agent], feed: ActionFeed, state: WorldState) -> str:
        """构建行为体的个性化观察：供应链邻居行动 + 全链高影响力行动。"""
        node_states = state.node_states or self._initial_node_states()
        type_downstream = self._type_level_links(node_states)
        relations = self._neighbor_relations(agent, agents, type_downstream)
        records = feed.for_agent(agent.id, set(relations))
        if not records:
            return "暂无可观察行动（首轮或近期其他行为体未行动）"
        return "\n".join(
            record.format_entry(relation=relations.get(record.agent_id, "全链广播"))
            for record in records
        )

    def _type_level_links(self, node_states: list[NodeState]) -> dict[str, set[str]]:
        """节点类型级的下游关系：{上游类型: {下游类型}}。无节点链路时用兜底主链。"""
        by_name = {node.name: node for node in node_states}
        type_links: dict[str, set[str]] = {}
        for upstream_name, downstream_names in self._node_links(node_states).items():
            upstream = by_name.get(upstream_name)
            if upstream is None:
                continue
            for name in downstream_names:
                downstream = by_name.get(name)
                if downstream is not None:
                    type_links.setdefault(upstream.node_type, set()).add(downstream.node_type)
        if type_links:
            return type_links
        return {
            upstream: {downstream}
            for upstream, downstream in zip(_FALLBACK_TYPE_CHAIN, _FALLBACK_TYPE_CHAIN[1:])
        }

    def _neighbor_relations(self, agent: Agent, agents: list[Agent], type_downstream: dict[str, set[str]]) -> dict[int, str]:
        """其他行为体相对本行为体的链路方位：{agent_id: "上游"|"下游"}。"""
        my_types = self._agent_node_types(agent)
        downstream_types: set[str] = set()
        for node_type in my_types:
            downstream_types.update(type_downstream.get(node_type, set()))
        upstream_types = {
            node_type
            for node_type, targets in type_downstream.items()
            if not my_types.isdisjoint(targets)
        }
        relations: dict[int, str] = {}
        for other in agents:
            if other.id == agent.id:
                continue
            other_types = self._agent_node_types(other)
            if not other_types.isdisjoint(upstream_types):
                relations[other.id] = "上游"
            elif not other_types.isdisjoint(downstream_types):
                relations[other.id] = "下游"
        return relations

    def _apply_bullwhip_effect(self, agents: list[Agent]) -> None:
        """牛鞭效应：上游行为体的波动被逐级放大。"""
        # 找到下游行为体（零售商、消费者）的 pressure 水平
        downstream = [a for a in agents if a.decision_stance == "aggressive"]
        if not downstream:
            return
        avg_downstream_pressure = sum(a.pressure for a in downstream) / len(downstream)
        if avg_downstream_pressure < 0.5:
            return
        # 向上游传播压力
        upstream = [a for a in agents if a.decision_stance in ("cautious", "cooperative")]
        for agent in upstream:
            if self._rng.random() < 0.3:
                agent.pressure = clamp(agent.pressure + avg_downstream_pressure * 0.15, 0.0, 1.0)
                agent.capacity = clamp(agent.capacity - 0.03, 0.3, 1.5)

    def _persist_round(self, state: WorldState, messages: list[dict[str, Any]]) -> None:
        repo = self.state.round_repository
        project_id = self.state.project_id
        simulation_id = self._simulation_record_id()
        if not repo or project_id is None or simulation_id is None:
            return
        repo.save(
            project_id=project_id,
            simulation_id=simulation_id,
            round_index=state.round,
            simulated_hour=state.simulated_hour,
            inventory_level=state.inventory_level,
            cost_index=state.cost_index,
            delivery_delay=state.delivery_delay,
            service_level=state.service_level,
            profit_margin=state.profit_margin,
            resilience_score=state.resilience_score,
            state=state.to_dict(),
            agent_messages=messages,
        )

    def _emit_callbacks(self, state: WorldState, messages: list[dict[str, Any]]) -> None:
        if self._progress_callback:
            self._progress_callback(
                state.round,
                self.state.total_rounds,
                f"第 {state.round}/{self.state.config.max_rounds} 轮",
            )
        if self._round_callback:
            self._round_callback(state, messages)

    def _clone_agents(self) -> list[Agent]:
        return [Agent.from_dict(agent.to_dict()) for agent in self.state.agents]

    @staticmethod
    def _snapshot_all(agents: list[Agent]) -> dict[int, AgentSnapshot]:
        return {
            agent.id: AgentSnapshot(
                agent_id=agent.id,
                pressure=agent.pressure,
                decision_stance=agent.decision_stance,
            )
            for agent in agents
        }

    @staticmethod
    def _agent_by_id(agents: list[Agent], agent_id: int) -> Agent:
        return next(agent for agent in agents if agent.id == agent_id)

    def _simulation_record_id(self) -> int | None:
        record = self.state.simulation_record
        if record is None:
            return None
        value = getattr(record, "id", record.get("id") if isinstance(record, dict) else None)
        return int(value) if value else None

    @staticmethod
    def _format_recent_events(state: WorldState) -> str:
        if not state.key_events:
            return "none"
        return "\n".join(f"- {event.description}" for event in state.key_events[-3:])

    def _retrieve_knowledge_context(self, agent: Agent, state: WorldState) -> str:
        repo = self.state.knowledge_repository
        if not repo or self.state.project_id is None:
            return "none"
        scenario = self.state.scenario or Scenario()
        query = "\n".join(
            [
                scenario.title,
                scenario.industry,
                scenario.background[:800],
                agent.name,
                agent.role,
                self._format_current_metrics(state),
                self._format_nodes_summary(state=state, agent=agent, relevant_only=True),
                self._format_recent_events(state),
            ]
        )
        chunks = repo.search(self.state.project_id, query, limit=4)
        if not chunks:
            return "none"
        return "\n".join(
            f"[{chunk.source}#{chunk.chunk_index + 1}] {chunk.content[:700]}"
            for chunk in chunks
        )

    def abort(self) -> None:
        """中止仿真。"""
        self.state.status = SimStatus.ABORTED

    def pause(self) -> None:
        """暂停仿真。"""
        if self.state.status == SimStatus.RUNNING:
            self.state.status = SimStatus.PAUSED

    def resume(self) -> None:
        """恢复仿真。"""
        if self.state.status == SimStatus.PAUSED:
            self.state.status = SimStatus.RUNNING

    # --- 节点状态子系统 ---

    @staticmethod
    def _agent_node_types(agent: Agent) -> set[str]:
        return set(AGENT_NODE_TYPES.get(agent.id, ()))

    def _agent_has_node_type(self, agent: Agent, node_type: str) -> bool:
        return node_type in self._agent_node_types(agent)

    @staticmethod
    def _format_current_metrics(state: WorldState) -> str:
        return (
            f"inventory_level={state.inventory_level:.1f}\n"
            f"cost_index={state.cost_index:.1f}\n"
            f"delivery_delay={state.delivery_delay:.2f}\n"
            f"service_level={state.service_level:.3f}\n"
            f"profit_margin={state.profit_margin:.3f}\n"
            f"resilience_score={state.resilience_score:.1f}"
        )

    def _initial_node_states(self) -> list[NodeState]:
        scenario = self.state.scenario or Scenario()
        nodes: list[NodeState] = []
        for raw in scenario.nodes or []:
            inventory = clamp(float(raw.get("inventory", scenario.initial_inventory)), 0.0, 100.0)
            capacity = max(0.0, float(raw.get("capacity", 0.0)))
            lead_time = max(0.0, float(raw.get("lead_time", 0.0)))
            cost_index = clamp(float(raw.get("cost_index", scenario.baseline_cost)), 0.0, 100.0)
            node = NodeState(
                name=str(raw.get("name", "node")),
                node_type=str(raw.get("type", "unknown")).strip().lower(),
                inventory=inventory,
                capacity=capacity,
                lead_time=lead_time,
                cost_index=cost_index,
                service_level=scenario.baseline_service_level,
                profit_margin=0.15,
            )
            node.resilience_score = self._score_node_resilience(node)
            nodes.append(node)
        return nodes

    def _build_node_states(self, previous: WorldState, agents: list[Agent], turns: list[AgentTurn]) -> list[NodeState]:
        source = previous.node_states or self._initial_node_states()
        node_states = [
            NodeState(
                name=node.name,
                node_type=node.node_type,
                inventory=node.inventory,
                capacity=node.capacity,
                lead_time=node.lead_time,
                cost_index=node.cost_index,
                service_level=node.service_level,
                profit_margin=node.profit_margin,
                resilience_score=node.resilience_score,
            )
            for node in source
        ]
        if not node_states:
            return []

        if not turns:
            for node in node_states:
                node.inventory = clamp(node.inventory + 0.6, 0.0, 100.0)
                node.cost_index = clamp(node.cost_index - 0.2, 0.0, 100.0)
                node.lead_time = max(0.0, node.lead_time - 0.05)
                node.service_level = clamp(node.service_level + 0.01, 0.0, 1.0)
                node.profit_margin = clamp(node.profit_margin + 0.005, -1.0, 1.0)
                node.resilience_score = self._score_node_resilience(node)
            return node_states

        for turn in turns:
            if turn.skipped:
                continue
            agent = self._agent_by_id(agents, turn.agent_id)
            node_types = self._agent_node_types(agent)
            targets = [node for node in node_states if node.node_type in node_types] or node_states
            share = 1.0 / len(targets)
            for node in targets:
                node.inventory = clamp(node.inventory + turn.inventory_change * share, 0.0, 100.0)
                node.cost_index = clamp(node.cost_index + turn.cost_change * share, 0.0, 100.0)
                node.lead_time = max(0.0, node.lead_time + turn.delay_change * share)
                node.service_level = clamp(node.service_level + turn.service_change * share, 0.0, 1.0)
                node.profit_margin = clamp(node.profit_margin + turn.margin_change * share, -1.0, 1.0)
                capacity_shift = (turn.service_change * 18.0 - max(turn.delay_change, 0.0) * 6.0) * share
                node.capacity = max(0.0, node.capacity + capacity_shift)
                node.resilience_score = self._score_node_resilience(node)
        self._propagate_supply_chain_links(node_states)
        return node_states

    @staticmethod
    def _aggregate_node_metrics(node_states: list[NodeState]) -> tuple[float, float, float, float, float, float]:
        weights = [(node, max(node.capacity, 1.0)) for node in node_states]
        inventory = _weighted_average([(node.inventory, weight) for node, weight in weights], 75.0)
        cost = _weighted_average([(node.cost_index, weight) for node, weight in weights], 50.0)
        delay = _weighted_average([(node.lead_time, weight) for node, weight in weights], 0.0)
        service = _weighted_average([(node.service_level, weight) for node, weight in weights], 0.85)
        margin = _weighted_average([(node.profit_margin, weight) for node, weight in weights], 0.15)
        resilience = _weighted_average([(node.resilience_score, weight) for node, weight in weights], 60.0)
        return (
            clamp(inventory, 0.0, 100.0),
            clamp(cost, 0.0, 100.0),
            max(0.0, delay),
            clamp(service, 0.0, 1.0),
            clamp(margin, -1.0, 1.0),
            clamp(resilience, 0.0, 100.0),
        )

    def _apply_events_to_node_states(self, node_states: list[NodeState], events: list[Any]) -> None:
        targets_by_event = {
            "raw_material_shortage": {"supplier", "manufacturer"},
            "warehouse_overflow": {"distributor", "retailer"},
            "price_war": {"retailer", "distributor", "consumer"},
            "regulatory_intervention": {"supplier", "manufacturer", "distributor", "retailer", "logistics"},
            "demand_surge": {"consumer", "retailer", "distributor", "manufacturer"},
        }
        for event in events:
            target_types = targets_by_event.get(getattr(event, "event_type", ""), set())
            targets = [node for node in node_states if not target_types or node.node_type in target_types] or node_states
            share = 1.0 / len(targets)
            for node in targets:
                node.inventory = clamp(node.inventory + event.inventory_delta * share, 0.0, 100.0)
                node.cost_index = clamp(node.cost_index + event.cost_delta * share, 0.0, 100.0)
                node.lead_time = max(0.0, node.lead_time + event.delay_delta * share)
                node.service_level = clamp(node.service_level + event.service_delta * share, 0.0, 1.0)
                node.profit_margin = clamp(node.profit_margin + event.margin_delta * share, -1.0, 1.0)
                node.capacity = max(0.0, node.capacity - max(event.delay_delta, 0.0) * 2.0 * share)
                node.resilience_score = self._score_node_resilience(node)

    def _propagate_supply_chain_links(self, node_states: list[NodeState]) -> None:
        links = self._node_links(node_states)
        if not links:
            return
        by_name = {node.name: node for node in node_states}
        for upstream_name, downstream_names in links.items():
            upstream = by_name.get(upstream_name)
            if upstream is None:
                continue
            for downstream_name in downstream_names:
                downstream = by_name.get(downstream_name)
                if downstream is None:
                    continue
                self._propagate_link_effect(upstream, downstream)
        for node in node_states:
            node.resilience_score = self._score_node_resilience(node)

    @staticmethod
    def _propagate_link_effect(upstream: NodeState, downstream: NodeState) -> None:
        shortage_pressure = max(0.0, (55.0 - upstream.inventory) / 55.0)
        delay_pressure = max(0.0, upstream.lead_time - 1.0)
        healthy_supply = max(0.0, (upstream.inventory - 55.0) / 45.0)
        downstream_need = max(0.0, (65.0 - downstream.inventory) / 65.0)

        if healthy_supply > 0 and downstream_need > 0:
            replenishment = min(healthy_supply * 3.0, downstream_need * 4.0, upstream.inventory * 0.04)
            upstream.inventory = clamp(upstream.inventory - replenishment * 0.35, 0.0, 100.0)
            downstream.inventory = clamp(downstream.inventory + replenishment, 0.0, 100.0)
            downstream.service_level = clamp(downstream.service_level + replenishment * 0.0025, 0.0, 1.0)
            downstream.lead_time = max(0.0, downstream.lead_time - replenishment * 0.01)

        if shortage_pressure > 0:
            downstream.inventory = clamp(downstream.inventory - shortage_pressure * 3.5, 0.0, 100.0)
            downstream.cost_index = clamp(downstream.cost_index + shortage_pressure * 1.8, 0.0, 100.0)
            downstream.service_level = clamp(downstream.service_level - shortage_pressure * 0.025, 0.0, 1.0)
            downstream.profit_margin = clamp(downstream.profit_margin - shortage_pressure * 0.015, -1.0, 1.0)

        if delay_pressure > 0:
            downstream.lead_time = max(0.0, downstream.lead_time + delay_pressure * 0.18)
            downstream.service_level = clamp(downstream.service_level - delay_pressure * 0.01, 0.0, 1.0)
            downstream.capacity = max(0.0, downstream.capacity - delay_pressure * 0.8)

        upstream.cost_index = clamp(upstream.cost_index + downstream_need * 0.4, 0.0, 100.0)
        upstream.capacity = max(0.0, upstream.capacity - shortage_pressure * 0.4 + healthy_supply * 0.2)

    def _node_links(self, node_states: list[NodeState]) -> dict[str, set[str]]:
        scenario = self.state.scenario or Scenario()
        scenario_nodes = {str(node.get("name", "")).strip(): node for node in scenario.nodes or []}
        links: dict[str, set[str]] = {}
        names = {node.name for node in node_states}

        for name, raw in scenario_nodes.items():
            if name not in names:
                continue
            downstream = {
                target for target in raw.get("downstream", [])
                if target in names and target != name
            }
            if downstream:
                links.setdefault(name, set()).update(downstream)

        for name, raw in scenario_nodes.items():
            if name not in names:
                continue
            for upstream_name in raw.get("upstream", []):
                if upstream_name in names and upstream_name != name:
                    links.setdefault(upstream_name, set()).add(name)

        if links:
            return links
        return self._infer_node_links(node_states)

    @staticmethod
    def _infer_node_links(node_states: list[NodeState]) -> dict[str, set[str]]:
        order_rank = {
            "supplier": 0,
            "manufacturer": 1,
            "distributor": 2,
            "retailer": 3,
            "consumer": 4,
        }
        chain_nodes = [node for node in node_states if node.node_type in order_rank]
        chain_nodes.sort(key=lambda node: (order_rank[node.node_type], node.name))
        links: dict[str, set[str]] = {}
        for current, nxt in zip(chain_nodes, chain_nodes[1:]):
            links.setdefault(current.name, set()).add(nxt.name)
        return links

    @staticmethod
    def _score_node_resilience(node: NodeState) -> float:
        return clamp(
            60.0
            + (node.inventory - 50.0) * 0.20
            - (node.cost_index - 50.0) * 0.25
            - node.lead_time * 4.0
            + node.service_level * 18.0
            + node.profit_margin * 25.0,
            0.0,
            100.0,
        )

    def _relevant_nodes_for_agent(self, state: WorldState | None = None, agent: Agent | None = None) -> list[NodeState | dict[str, Any]]:
        if state and state.node_states:
            nodes: list[NodeState | dict[str, Any]] = list(state.node_states)
        else:
            scenario = self.state.scenario or Scenario()
            nodes = list(scenario.nodes or [])
        if agent is None:
            return nodes
        node_types = self._agent_node_types(agent)
        if not node_types:
            return nodes
        relevant: list[NodeState | dict[str, Any]] = []
        for node in nodes:
            node_type = node.node_type if isinstance(node, NodeState) else str(node.get("type", "")).strip().lower()
            if node_type in node_types:
                relevant.append(node)
        return relevant or nodes

    def _format_nodes_summary(self, state: WorldState | None = None, agent: Agent | None = None, relevant_only: bool = False) -> str:
        nodes = self._relevant_nodes_for_agent(state=state, agent=agent) if relevant_only else self._relevant_nodes_for_agent(state=state)
        if not nodes:
            return "none"
        lines = []
        for node in nodes[:8]:
            if isinstance(node, NodeState):
                lines.append(
                    f"- {node.name} "
                    f"[type={node.node_type}, inventory={node.inventory:.1f}, "
                    f"capacity={node.capacity:.1f}, lead_time={node.lead_time:.2f}, "
                    f"cost_index={node.cost_index:.1f}, service_level={node.service_level:.2f}]"
                )
            else:
                lines.append(
                    f"- {node.get('name', 'node')} "
                    f"[type={node.get('type', 'unknown')}, "
                    f"inventory={node.get('inventory', 0)}, "
                    f"capacity={node.get('capacity', 0)}, "
                    f"lead_time={node.get('lead_time', 0)}, "
                    f"cost_index={node.get('cost_index', 50)}]"
                )
        return "\n".join(lines)


def _weighted_average(values: list[tuple[float, float]], fallback: float) -> float:
    """加权平均工具函数。"""
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return fallback
    return sum(value * weight for value, weight in values) / total_weight
