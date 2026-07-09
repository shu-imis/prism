"""仿真引擎 —— 真实 LLM 多智能体主循环。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Any, Callable, Optional

from config import app_config
from core.agent import Agent
from core.events import EventDetector
from core.scenario_parser import Scenario
from core.world_state import AgentSnapshot, WorldState
from db.models import Checkpoint, CheckpointRepository, KnowledgeRepository, SimulationRoundRepository
from llm.client import LLMClient
from llm.prompts import AGENT_RESPONSE_SYSTEM, OFFICIAL_SPEECH_SYSTEM


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
    hours_per_round: int = 4
    strategies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulationState:
    """仿真运行时状态。"""

    config: SimulationConfig = field(default_factory=SimulationConfig)
    status: SimStatus = SimStatus.IDLE
    current_round: int = 0
    total_rounds: int = 0
    strategy_index: int = 0
    strategy_results: list[list[WorldState]] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)
    scenario: Optional[Scenario] = None
    error_message: str = ""
    project_id: int | None = None
    strategy_records: list[Any] = field(default_factory=list)
    round_repository: SimulationRoundRepository | None = None
    checkpoint_repository: CheckpointRepository | None = None
    knowledge_repository: KnowledgeRepository | None = None
    resume_checkpoint: Checkpoint | None = None
    round_timeout: int = 120


@dataclass
class AgentTurn:
    """单个 Agent 在一轮中的 LLM 输出。"""

    agent_id: int
    agent_name: str
    role: str
    stance: str
    speech: str
    emotion_change: float = 0.0
    trust_change: float = 0.0
    spread_intent: float = 0.0
    stance_shift: str = "none"
    tone: str = ""
    is_official: bool = False
    skipped: bool = False
    error_message: str = ""
    warning: str = ""

    def to_message(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "stance": self.stance,
            "content": self.speech,
            "metrics": {
                "emotion_change": self.emotion_change,
                "trust_change": self.trust_change,
                "spread_intent": self.spread_intent,
                "stance_shift": self.stance_shift,
                "tone": self.tone,
                "is_official": self.is_official,
                "skipped": self.skipped,
                "error_message": self.error_message,
                "warning": self.warning,
            },
        }


RoundCallback = Callable[[int, dict[str, Any], WorldState, list[dict[str, Any]]], None]


class SimulationRecoverableError(RuntimeError):
    """仿真已保存检查点，可修复配置后恢复。"""


class SimulationEngine:
    """管理多策略、多轮、多 Agent 的真实 LLM 推演生命周期。"""

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
        strategies: list[dict[str, Any]],
        max_rounds: int | None = None,
        *,
        project_id: int | None = None,
        strategy_records: list[Any] | None = None,
        round_repository: SimulationRoundRepository | None = None,
        checkpoint_repository: CheckpointRepository | None = None,
        knowledge_repository: KnowledgeRepository | None = None,
        resume_checkpoint: Checkpoint | None = None,
        round_timeout: int | None = None,
    ) -> None:
        """配置仿真参数。"""

        self.state.config = SimulationConfig(
            max_rounds=max_rounds or app_config.sim.max_rounds,
            hours_per_round=app_config.sim.hours_per_round,
            strategies=strategies,
        )
        self.state.agents = agents
        self.state.scenario = scenario
        self.state.total_rounds = self.state.config.max_rounds * len(strategies)
        self.state.strategy_results = []
        self.state.status = SimStatus.IDLE
        self.state.project_id = project_id
        self.state.strategy_records = list(strategy_records or [])
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
        """设置轮次回调 —— 用于 UI 展示每轮状态和 Agent 发言。"""

        self._round_callback = callback

    def run(self) -> list[list[WorldState]]:
        """运行完整仿真（同步模式，UI 应放在线程中调用）。"""

        if not self.state.config.strategies:
            raise ValueError("至少需要配置一个回应策略。")
        if not self.state.agents:
            raise ValueError("至少需要配置一个 Agent。")

        self.state.status = SimStatus.RUNNING
        self.state.strategy_results = self._resume_strategy_results()

        try:
            start_strategy = self._resume_strategy_index()
            for strategy_index in range(start_strategy, len(self.state.config.strategies)):
                strategy = self.state.config.strategies[strategy_index]
                self.state.strategy_index = strategy_index
                if self.state.status == SimStatus.ABORTED:
                    break

                rounds = self._run_strategy_simulation(strategy_index, strategy)
                if len(self.state.strategy_results) > strategy_index:
                    self.state.strategy_results[strategy_index] = rounds
                else:
                    self.state.strategy_results.append(rounds)

            if self.state.status != SimStatus.ABORTED:
                self.state.status = SimStatus.COMPLETED
                self._delete_checkpoints()

        except Exception as exc:
            self.state.status = SimStatus.ERROR
            self.state.error_message = str(exc)
            raise

        return self.state.strategy_results

    def _run_strategy_simulation(self, strategy_index: int, strategy: dict[str, Any]) -> list[WorldState]:
        hours_per_round = self.state.config.hours_per_round
        max_rounds = self.state.config.max_rounds
        detector = EventDetector()
        resume = self._resume_for_strategy(strategy_index)
        if resume:
            agents = [Agent.from_dict(item) for item in resume.get("agents", [])]
            rounds = [WorldState.from_dict(item) for item in resume.get("current_rounds", [])]
            official_released = bool(resume.get("official_released", False))
            start_round = int(resume.get("last_round", 0)) + 1
            ws = rounds[-1] if rounds else self._initial_world_state(agents)
        else:
            agents = self._clone_agents()
            official_released = False
            rounds = [self._initial_world_state(agents)]
            ws = rounds[0]
            start_round = 1
            self._persist_round(strategy_index, ws, [])
            self._save_checkpoint(strategy_index, ws, agents, official_released, rounds)

        for round_index in range(start_round, max_rounds + 1):
            self._wait_if_paused()
            if self.state.status == SimStatus.ABORTED:
                self._save_checkpoint(strategy_index, ws, agents, official_released, rounds)
                break

            round_started = time.monotonic()
            simulated_hour = round_index * hours_per_round
            active_agents = self._select_active_agents(agents, simulated_hour)
            release_hour = int(self._strategy_value(strategy, "release_hour", 4))
            official_agent = self._official_agent(agents)
            if official_agent and not official_released and simulated_hour >= release_hour:
                active_agents.append(official_agent)
                official_released = True

            turns: list[AgentTurn] = []
            for agent in active_agents:
                self._wait_if_paused()
                if self.state.status == SimStatus.ABORTED:
                    break
                if time.monotonic() - round_started > self.state.round_timeout:
                    turns.append(self._skipped_turn(agent, "本轮超过最大耗时，已跳过剩余 Agent。", warning="round_timeout"))
                    continue
                try:
                    if agent.id == 8:
                        turn = self._generate_official_turn(agent, ws, strategy)
                    else:
                        turn = self._generate_agent_turn(agent, ws, strategy)
                    self._apply_agent_turn(agent, turn)
                except Exception as exc:  # noqa: BLE001 - LLM SDK 错误类型不统一
                    turn = self._skipped_turn(agent, str(exc))
                turns.append(turn)

            next_state = self._build_next_state(
                previous=ws,
                agents=agents,
                turns=turns,
                round_index=round_index,
                simulated_hour=simulated_hour,
            )
            events = detector.detect(
                next_state,
                kol_spoke=any(t.agent_id == 4 and not t.skipped for t in turns),
                kol_speech="\n".join(t.speech for t in turns if t.agent_id == 4 and not t.skipped),
                regulator_spoke=any(t.agent_id == 6 and not t.skipped for t in turns),
                regulator_speech="\n".join(t.speech for t in turns if t.agent_id == 6 and not t.skipped),
                competitor_spoke=any(t.agent_id == 7 and not t.skipped for t in turns),
            )
            self._apply_events(next_state, agents, events)
            self._apply_group_dynamics(agents)
            self._propagate_memory(agents, turns)

            rounds.append(next_state)
            ws = next_state
            messages = [turn.to_message() for turn in turns]
            self._persist_round(strategy_index, ws, messages)
            self._save_checkpoint(strategy_index, ws, agents, official_released, rounds)
            self._emit_callbacks(strategy_index, strategy, ws, messages)
            if active_agents and all(turn.skipped for turn in turns):
                raise SimulationRecoverableError(
                    f"策略 {strategy_index + 1} 第 {round_index} 轮所有激活 Agent 均调用失败或超时，已保存检查点。"
                )

        return rounds

    def _ensure_llm_client(self) -> LLMClient:
        if self.llm_client is None:
            self.llm_client = LLMClient.from_env()
        return self.llm_client

    def _initial_world_state(self, agents: list[Agent]) -> WorldState:
        return WorldState(
            round=0,
            simulated_hour=0,
            heat=self.state.scenario.initial_heat if self.state.scenario else 0.0,
            sentiment=self.state.scenario.baseline_sentiment if self.state.scenario else 0.0,
            support_rate=0.5,
            agent_states=self._snapshot_all(agents),
        )

    def _resume_strategy_index(self) -> int:
        if not self._resume_payload:
            return 0
        return int(self._resume_payload.get("strategy_index", 0))

    def _resume_strategy_results(self) -> list[list[WorldState]]:
        if not self._resume_payload:
            return []
        return [
            [WorldState.from_dict(item) for item in strategy_rounds]
            for strategy_rounds in self._resume_payload.get("strategy_results", [])
        ]

    def _resume_for_strategy(self, strategy_index: int) -> dict[str, Any] | None:
        if not self._resume_payload:
            return None
        if int(self._resume_payload.get("strategy_index", -1)) != strategy_index:
            return None
        return self._resume_payload

    def _save_checkpoint(
        self,
        strategy_index: int,
        state: WorldState,
        agents: list[Agent],
        official_released: bool,
        current_rounds: list[WorldState],
    ) -> None:
        repo = self.state.checkpoint_repository
        project_id = self.state.project_id
        strategy_id = self._strategy_record_id(strategy_index)
        if not repo or project_id is None or strategy_id is None:
            return
        strategy_results = [
            [round_state.to_dict() for round_state in strategy_rounds]
            for strategy_rounds in self.state.strategy_results[:strategy_index]
        ]
        engine_state = {
            "strategy_index": strategy_index,
            "last_round": state.round,
            "official_released": official_released,
            "agents": [agent.to_dict() for agent in agents],
            "current_rounds": [round_state.to_dict() for round_state in current_rounds],
            "strategy_results": strategy_results,
            "scenario": self.state.scenario.to_dict() if self.state.scenario else {},
            "strategies": self.state.config.strategies,
            "max_rounds": self.state.config.max_rounds,
        }
        repo.save(
            project_id=project_id,
            strategy_id=strategy_id,
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
            stance=agent.stance,
            speech="",
            skipped=True,
            error_message=error_message,
            warning=warning,
        )

    def _generate_agent_turn(self, agent: Agent, state: WorldState, strategy: dict[str, Any]) -> AgentTurn:
        scenario = self.state.scenario or Scenario()
        system_prompt = AGENT_RESPONSE_SYSTEM.format(
            agent_profile=agent.profile,
            simulated_hour=state.simulated_hour,
            heat=f"{state.heat:.1f}",
            sentiment=f"{state.sentiment:.2f}",
            support_rate=f"{state.support_rate:.1%}",
            emotion=f"{agent.emotion:.2f}",
            trust=f"{agent.trust:.2f}",
            recent_events=self._format_recent_events(state),
            memory="\n".join(agent.memory[-5:]) or "暂无",
        )
        user_message = (
            f"事件标题：{scenario.title}\n"
            f"行业：{scenario.industry}\n"
            f"事件背景：{scenario.background}\n"
            f"企业现有声明：{scenario.company_statement or '暂无'}\n"
            f"当前策略：{self._strategy_value(strategy, 'name', '未命名策略')}\n"
            f"策略声明稿：{self._strategy_value(strategy, 'statement', '')}\n"
            f"相关背景资料片段：\n{self._retrieve_knowledge_context(agent, state, strategy)}\n"
            "请只返回 JSON 对象。"
        )
        data = self._ensure_llm_client().chat_json(system_prompt, user_message, temperature=0.35)
        return AgentTurn(
            agent_id=agent.id,
            agent_name=agent.name,
            role=agent.role,
            stance=agent.stance,
            speech=str(data.get("speech", "")).strip(),
            emotion_change=_clamp_float(data.get("emotion_change", 0.0), -0.3, 0.3),
            trust_change=_clamp_float(data.get("trust_change", 0.0), -0.2, 0.2),
            spread_intent=_clamp_float(data.get("spread_intent", 0.2), 0.0, 1.0),
            stance_shift=str(data.get("stance_shift", "none")),
        )

    def _generate_official_turn(self, agent: Agent, state: WorldState, strategy: dict[str, Any]) -> AgentTurn:
        statement = str(self._strategy_value(strategy, "statement", ""))
        system_prompt = OFFICIAL_SPEECH_SYSTEM.format(
            company_statement=statement,
            simulated_hour=state.simulated_hour,
            heat=f"{state.heat:.1f}",
            sentiment=f"{state.sentiment:.2f}",
        )
        scenario = self.state.scenario or Scenario()
        user_message = (
            f"事件标题：{scenario.title}\n"
            f"事件背景：{scenario.background}\n"
            f"相关背景资料片段：\n{self._retrieve_knowledge_context(agent, state, strategy)}\n"
            "请只返回 JSON 对象。"
        )
        data = self._ensure_llm_client().chat_json(system_prompt, user_message, temperature=0.2)
        tone = str(data.get("tone", "transparent"))
        trust_change = 0.12 if tone in {"apologetic", "conciliatory", "transparent"} else -0.04
        emotion_change = 0.08 if tone in {"apologetic", "conciliatory", "transparent"} else -0.03
        spread_intent = 0.45 if tone in {"transparent", "assertive"} else 0.30
        return AgentTurn(
            agent_id=agent.id,
            agent_name=agent.name,
            role=agent.role,
            stance=agent.stance,
            speech=str(data.get("speech", statement)).strip(),
            emotion_change=emotion_change,
            trust_change=trust_change,
            spread_intent=spread_intent,
            stance_shift="toward_supportive",
            tone=tone,
            is_official=True,
        )

    def _build_next_state(
        self,
        *,
        previous: WorldState,
        agents: list[Agent],
        turns: list[AgentTurn],
        round_index: int,
        simulated_hour: int,
    ) -> WorldState:
        weighted_emotion = _weighted_average([(agent.emotion, agent.influence) for agent in agents], previous.sentiment)
        weighted_trust = _weighted_average([(agent.trust, agent.influence) for agent in agents], previous.support_rate)
        non_official_heat = sum(
            self._agent_by_id(agents, turn.agent_id).influence * turn.spread_intent * self._spread_multiplier(turn)
            for turn in turns
            if not turn.is_official and not turn.skipped
        )
        official_adjust = sum(self._official_heat_adjust(turn) for turn in turns if turn.is_official)
        quiet_cooling = -1.2 if not turns else 0.0
        heat = _clamp(previous.heat + non_official_heat + official_adjust + quiet_cooling, 0.0, 100.0)
        sentiment = _clamp(previous.sentiment * 0.55 + weighted_emotion * 0.45, -1.0, 1.0)
        support_rate = _clamp(previous.support_rate * 0.65 + weighted_trust * 0.35, 0.0, 1.0)

        snapshots = self._snapshot_all(agents)
        for turn in turns:
            agent = self._agent_by_id(agents, turn.agent_id)
            snapshots[agent.id] = AgentSnapshot(
                agent_id=agent.id,
                emotion=agent.emotion,
                trust=agent.trust,
                stance=agent.stance,
                spoke=not turn.skipped,
                speech=turn.speech if not turn.skipped else f"跳过：{turn.error_message[:120]}",
            )

        return WorldState(
            round=round_index,
            simulated_hour=simulated_hour,
            heat=heat,
            sentiment=sentiment,
            support_rate=support_rate,
            agent_states=snapshots,
        )

    def _apply_events(self, state: WorldState, agents: list[Agent], events) -> None:
        state.key_events = events
        for event in events:
            state.heat = _clamp(state.heat + event.heat_delta, 0.0, 100.0)
            state.sentiment = _clamp(state.sentiment + event.sentiment_delta, -1.0, 1.0)
            state.support_rate = _clamp(state.support_rate + event.trust_delta, 0.0, 1.0)
            if event.trust_delta:
                for agent in agents:
                    agent.trust = _clamp(agent.trust + event.trust_delta, 0.0, 1.0)

    def _apply_agent_turn(self, agent: Agent, turn: AgentTurn) -> None:
        if turn.skipped:
            return
        agent.emotion = _clamp(agent.emotion + turn.emotion_change, -1.0, 1.0)
        agent.trust = _clamp(agent.trust + turn.trust_change, 0.0, 1.0)
        if turn.stance_shift == "toward_opposing":
            agent.stance = _shift_stance(agent.stance, toward="opposing")
        elif turn.stance_shift == "toward_supportive":
            agent.stance = _shift_stance(agent.stance, toward="supportive")

    def _select_active_agents(self, agents: list[Agent], simulated_hour: int) -> list[Agent]:
        start = simulated_hour - self.state.config.hours_per_round
        window = {(start + offset) % 24 for offset in range(self.state.config.hours_per_round)}
        active: list[Agent] = []
        for agent in agents:
            if agent.id == 8:
                continue
            active_hours = set(agent.active_hours or range(24))
            if window.intersection(active_hours) and self._rng.random() <= agent.activity:
                active.append(agent)
        return active

    def _propagate_memory(self, agents: list[Agent], turns: list[AgentTurn]) -> None:
        influential = [
            turn
            for turn in turns
            if (
                not turn.skipped
                and turn.speech
                and (turn.spread_intent >= 0.6 or self._agent_by_id(agents, turn.agent_id).influence >= 1.5)
            )
        ]
        for agent in agents:
            for turn in influential:
                if turn.agent_id == agent.id:
                    continue
                source = "KOL 二次扩散" if turn.agent_id == 4 else turn.agent_name
                influence = self._agent_by_id(agents, turn.agent_id).influence
                agent.memory.append(f"{source}｜影响力 {influence:.1f}: {turn.speech[:90]}")
            agent.memory = agent.memory[-5:]

    def _apply_group_dynamics(self, agents: list[Agent]) -> None:
        opposing = [agent for agent in agents if agent.stance == "opposing"]
        neutral = [agent for agent in agents if agent.stance == "neutral"]
        if not opposing or not neutral:
            return
        negative_ratio = sum(1 for agent in opposing if agent.emotion <= -0.35) / len(opposing)
        if negative_ratio < 0.6:
            return
        for agent in neutral:
            if self._rng.random() < 0.35:
                agent.stance = "opposing"
                agent.trust = _clamp(agent.trust - 0.08, 0.0, 1.0)

    @staticmethod
    def _spread_multiplier(turn: AgentTurn) -> float:
        if turn.agent_id == 4:
            return 2.35  # 基础 2.2 + KOL 二次传播约 0.15
        return 2.2

    def _persist_round(self, strategy_index: int, state: WorldState, messages: list[dict[str, Any]]) -> None:
        repo = self.state.round_repository
        project_id = self.state.project_id
        strategy_id = self._strategy_record_id(strategy_index)
        if not repo or project_id is None or strategy_id is None:
            return
        repo.save(
            project_id=project_id,
            strategy_id=strategy_id,
            round_index=state.round,
            simulated_hour=state.simulated_hour,
            heat=state.heat,
            sentiment=state.sentiment,
            support_rate=state.support_rate,
            state=state.to_dict(),
            agent_messages=messages,
        )

    def _emit_callbacks(
        self,
        strategy_index: int,
        strategy: dict[str, Any],
        state: WorldState,
        messages: list[dict[str, Any]],
    ) -> None:
        if self._progress_callback:
            total = self.state.total_rounds
            current = strategy_index * self.state.config.max_rounds + state.round
            self._progress_callback(
                current,
                total,
                f"策略 {strategy_index + 1} · 第 {state.round}/{self.state.config.max_rounds} 轮",
            )
        if self._round_callback:
            self._round_callback(strategy_index, strategy, state, messages)

    def _clone_agents(self) -> list[Agent]:
        return [Agent.from_dict(agent.to_dict()) for agent in self.state.agents]

    @staticmethod
    def _snapshot_all(agents: list[Agent]) -> dict[int, AgentSnapshot]:
        return {
            agent.id: AgentSnapshot(
                agent_id=agent.id,
                emotion=agent.emotion,
                trust=agent.trust,
                stance=agent.stance,
            )
            for agent in agents
        }

    @staticmethod
    def _official_agent(agents: list[Agent]) -> Agent | None:
        return next((agent for agent in agents if agent.id == 8), None)

    @staticmethod
    def _agent_by_id(agents: list[Agent], agent_id: int) -> Agent:
        return next(agent for agent in agents if agent.id == agent_id)

    def _strategy_record_id(self, strategy_index: int) -> int | None:
        if strategy_index >= len(self.state.strategy_records):
            return None
        record = self.state.strategy_records[strategy_index]
        value = getattr(record, "id", record.get("id") if isinstance(record, dict) else None)
        return int(value) if value else None

    @staticmethod
    def _strategy_value(strategy: Any, key: str, default: Any = None) -> Any:
        if isinstance(strategy, dict):
            return strategy.get(key, default)
        return getattr(strategy, key, default)

    @staticmethod
    def _format_recent_events(state: WorldState) -> str:
        if not state.key_events:
            return "暂无"
        return "\n".join(f"- {event.description}" for event in state.key_events[-3:])

    def _retrieve_knowledge_context(self, agent: Agent, state: WorldState, strategy: dict[str, Any]) -> str:
        repo = self.state.knowledge_repository
        if not repo or self.state.project_id is None:
            return "暂无"
        scenario = self.state.scenario or Scenario()
        query = "\n".join(
            [
                scenario.title,
                scenario.industry,
                scenario.background[:800],
                self._strategy_value(strategy, "name", ""),
                self._strategy_value(strategy, "statement", "")[:800],
                agent.role,
                agent.stance,
                self._format_recent_events(state),
            ]
        )
        chunks = repo.search(self.state.project_id, query, limit=4)
        if not chunks:
            return "暂无"
        return "\n".join(
            f"[{chunk.source}#{chunk.chunk_index + 1}] {chunk.content[:700]}"
            for chunk in chunks
        )

    @staticmethod
    def _official_heat_adjust(turn: AgentTurn) -> float:
        if turn.tone in {"apologetic", "conciliatory", "transparent"}:
            return -4.0
        if turn.tone in {"defensive", "assertive"}:
            return 2.0
        return -1.0

    def abort(self) -> None:
        """中止仿真。"""

        self.state.status = SimStatus.ABORTED

    def pause(self) -> None:
        """暂停仿真。同步 demo 模式下仅标记状态。"""

        if self.state.status == SimStatus.RUNNING:
            self.state.status = SimStatus.PAUSED

    def resume(self) -> None:
        """恢复仿真。"""

        if self.state.status == SimStatus.PAUSED:
            self.state.status = SimStatus.RUNNING


def _weighted_average(values: list[tuple[float, float]], fallback: float) -> float:
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return fallback
    return sum(value * weight for value, weight in values) / total_weight


def _shift_stance(current: str, *, toward: str) -> str:
    if toward == "opposing":
        if current == "supportive":
            return "neutral"
        return "opposing"
    if current == "opposing":
        return "neutral"
    return "supportive"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _clamp_float(value: Any, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return _clamp(parsed, lower, upper)
