"""仿真引擎 —— 主循环

协调 Agent、WorldState、LLM 调用，执行多轮仿真。
参考 MiroFish SimulationRunner 的子进程 + 监控模式。
Day 1 版：定义接口和数据流，后续接入 LLM 完成完整仿真。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable

from prism.core.agent import Agent
from prism.core.world_state import WorldState, KeyEvent
from prism.core.events import EventDetector
from prism.core.scenario_parser import Scenario
from prism.config import app_config


class SimStatus(str, Enum):
    """仿真运行状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class SimulationConfig:
    """单次仿真的运行配置"""
    max_rounds: int = 12
    hours_per_round: int = 4
    strategies: List[dict] = field(default_factory=list)  # 策略列表


@dataclass
class SimulationState:
    """仿真运行时状态"""
    config: SimulationConfig = field(default_factory=SimulationConfig)
    status: SimStatus = SimStatus.IDLE
    current_round: int = 0
    total_rounds: int = 0
    strategy_index: int = 0               # 当前运行的策略索引
    strategy_results: List[List[WorldState]] = field(default_factory=list)
    agents: List[Agent] = field(default_factory=list)
    scenario: Optional[Scenario] = None
    error_message: str = ""


class SimulationEngine:
    """仿真引擎 —— 管理仿真生命周期

    设计借鉴 MiroFish：
      - 分层状态（SimulationConfig → SimulationState）
      - 进度回调（progress_callback）
      - 检查点机制（后续迭代）
    """

    def __init__(self):
        self.state = SimulationState()
        self._detector = EventDetector()
        self._progress_callback: Optional[Callable] = None

    def configure(
        self,
        agents: List[Agent],
        scenario: Scenario,
        strategies: List[dict],
        max_rounds: int | None = None,
    ):
        """配置仿真参数"""
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

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """设置进度回调 —— 用于 UI 更新"""
        self._progress_callback = callback

    def run(self) -> List[List[WorldState]]:
        """运行完整仿真（同步模式）"""
        self.state.status = SimStatus.RUNNING
        self.state.strategy_results = []

        try:
            for si, strategy in enumerate(self.state.config.strategies):
                self.state.strategy_index = si
                if self.state.status == SimStatus.ABORTED:
                    break

                rounds = self._run_strategy_simulation(strategy)
                self.state.strategy_results.append(rounds)

            if self.state.status != SimStatus.ABORTED:
                self.state.status = SimStatus.COMPLETED

        except Exception as e:
            self.state.status = SimStatus.ERROR
            self.state.error_message = str(e)
            raise

        return self.state.strategy_results

    def _run_strategy_simulation(self, strategy: dict) -> List[WorldState]:
        """运行单个策略的完整仿真"""
        hours_per_round = self.state.config.hours_per_round
        max_rounds = self.state.config.max_rounds
        rounds: List[WorldState] = []

        # 初始化世界状态
        ws = WorldState(
            round=0,
            simulated_hour=0,
            heat=self.state.scenario.initial_heat if self.state.scenario else 0,
            sentiment=self.state.scenario.baseline_sentiment if self.state.scenario else 0,
        )
        rounds.append(ws)

        for r in range(1, max_rounds + 1):
            if self.state.status == SimStatus.ABORTED:
                break

            # 时间推进
            ws = WorldState(
                round=r,
                simulated_hour=r * hours_per_round,
                heat=ws.heat,
                sentiment=ws.sentiment,
                support_rate=ws.support_rate,
            )

            # TODO: Day 3+ — 调用 LLM 执行实际仿真逻辑
            # 1. 激活判定
            # 2. 策略触发（官方发言人）
            # 3. 上下文构建
            # 4. Agent 生成反应（LLM）
            # 5. 状态更新
            # 6. 关键事件检测
            # 7. 检查点写入

            rounds.append(ws)

            # 进度回调
            if self._progress_callback:
                total = self.state.total_rounds
                current = self.state.strategy_index * max_rounds + r
                self._progress_callback(current, total, f"策略 {self.state.strategy_index + 1} · 第 {r}/{max_rounds} 轮")

        return rounds

    def abort(self):
        """中止仿真"""
        self.state.status = SimStatus.ABORTED

    def pause(self):
        """暂停仿真"""
        if self.state.status == SimStatus.RUNNING:
            self.state.status = SimStatus.PAUSED

    def resume(self):
        """恢复仿真"""
        if self.state.status == SimStatus.PAUSED:
            self.state.status = SimStatus.RUNNING
