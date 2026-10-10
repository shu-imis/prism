"""仿真服务：运行准备、历史装载与状态收尾。

页面通过本模块访问仿真数据，不直触 Repository。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from config import DB_PATH
from core.agent_factory import AgentFactory
from core.scenario_parser import Scenario
from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from core.world_state import WorldState
from db.database import Database
from db.models import (
    Checkpoint,
    CheckpointRepository,
    KnowledgeRepository,
    ProjectRepository,
    SimulationRepository,
    SimulationRound,
    SimulationRoundRepository,
    invalidate_simulation_results,
)
from llm.analysis import analyze_evolution
from llm.client import LLMClient
from llm.config import build_llm_client
from llm.prompts import AGENT_RESPONSE_SYSTEM
from report.generator import ReportGenerator, SimulationReport

_logger = logging.getLogger(__name__)


@dataclass
class SimulationHistory:
    """历史回显所需的仿真数据。"""

    rounds: list[SimulationRound]
    has_checkpoint: bool
    status: str | None


class SimulationRun:
    """单次仿真的执行单元：装载项目数据、驱动引擎并生成报告。

    在工作线程中运行，不依赖 Qt；进度与轮次经回调播报，状态落库
    交由服务方法与调用方处理。
    """

    def __init__(
        self,
        project_id: int | None,
        llm: LLMClient,
        rounds: int,
        engine: SimulationEngine,
        *,
        checkpoint: Checkpoint | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
        on_round: Callable[[WorldState, list[dict[str, Any]]], None] | None = None,
    ):
        self.project_id = project_id
        self.llm = llm
        self.rounds = rounds
        self.engine = engine
        self.checkpoint = checkpoint
        self.on_progress = on_progress
        self.on_round = on_round
        self._project_name = ""
        self._scenario_background = ""

    def run(self) -> list[WorldState]:
        """装载项目数据、配置引擎并执行仿真，返回轮次结果。"""
        db = Database(DB_PATH)
        try:
            project = (
                ProjectRepository(db).get_by_id(self.project_id)
                if self.project_id
                else None
            )
            scenario_dict = project.scenario if project else {}
            scenario = Scenario.from_dict(scenario_dict)
            self._project_name = project.name if project else ""
            self._scenario_background = scenario.background
            simulation_record = (
                SimulationRepository(db).get_or_create_main(self.project_id)
                if self.project_id
                else None
            )
            agents = AgentFactory.create_all()
            AgentFactory.apply_overrides(agents, scenario_dict.get("agents_config"))

            self.engine.configure(
                agents,
                scenario,
                system_prompt=AGENT_RESPONSE_SYSTEM,
                seed_events=scenario_dict.get("seed_events", []),
                max_rounds=self.rounds,
                project_id=self.project_id,
                simulation_record=simulation_record,
                round_repository=SimulationRoundRepository(db),
                checkpoint_repository=CheckpointRepository(db),
                knowledge_repository=KnowledgeRepository(db) if self.project_id else None,
                resume_checkpoint=self.checkpoint,
            )
            self.engine.set_progress_callback(self.on_progress)
            self.engine.set_round_callback(self.on_round)
            return self.engine.run()
        except SimulationRecoverableError:
            raise
        except Exception:
            # 致命错误：清除断点，防止反复恢复到同一错误
            if self.project_id:
                try:
                    CheckpointRepository(db).delete_for_project(self.project_id)
                except Exception:
                    pass
            raise
        finally:
            db.close()

    def build_report(self, results: list[WorldState]) -> SimulationReport:
        """按轮次结果生成报告，并附 AI 综合分析；失败时降级为纯公式结果。"""
        generator = ReportGenerator(self._project_name, self._scenario_background)
        generator.set_simulation_result(results)
        report = generator.generate()
        try:
            report.ai_analysis = analyze_evolution(self.llm, report, results)
        except Exception as e:
            _logger.warning("AI 综合分析失败，报告降级为纯公式结果：%s", e)
        return report


class SimulationService:
    """仿真运行、历史装载与状态收尾的服务入口。"""

    def load_history(self, project_id: int) -> SimulationHistory:
        """装载主仿真的轮次历史、断点有无与项目状态。"""
        main = SimulationRepository().get_main(project_id)
        rounds = SimulationRoundRepository().list_by_simulation(main.id) if main else []
        project = ProjectRepository().get_by_id(project_id)
        return SimulationHistory(
            rounds=rounds,
            has_checkpoint=bool(CheckpointRepository().latest_for_project(project_id)),
            status=project.status if project else None,
        )

    def prepare_start(self, project_id: int | None) -> tuple[LLMClient | None, Checkpoint | None]:
        """启动前准备：构造 LLM 客户端、判定断点并把项目置为运行中。

        有断点时返回断点供恢复；无断点时清空上次运行的轮次，避免轮次
        upsert 跨次混杂。LLM 客户端不可用时返回 (None, None)，不改动项目数据。
        """
        llm = build_llm_client(max_retries=1)
        if llm is None:
            return None, None
        checkpoint = None
        if project_id:
            checkpoint = CheckpointRepository().latest_for_project(project_id)
            if checkpoint is None:
                main = SimulationRepository().get_main(project_id)
                if main:
                    SimulationRoundRepository().delete_for_simulation(main.id)
            project = ProjectRepository().get_by_id(project_id)
            if project and project.status != "running":
                ProjectRepository().update_scenario(
                    project_id, dict(project.scenario), status="running"
                )
        return llm, checkpoint

    def mark_interrupted(self, project_id: int | None) -> None:
        """可恢复失败：项目标记为中断，保留断点恢复入口。"""
        self._set_status(project_id, "interrupted")

    def mark_draft(self, project_id: int | None) -> None:
        """启动失败：运行中的项目回退草稿。"""
        self._set_status(project_id, "draft", only_from="running")

    def finish_success(self, project_id: int | None) -> None:
        """仿真完成：项目标记为已完成。"""
        self._set_status(project_id, "completed")

    def clear_results(self, project_id: int) -> None:
        """作废仿真轮次、断点与报告，项目回到草稿态。"""
        invalidate_simulation_results(project_id)

    # --- 内部 ---

    @staticmethod
    def _set_status(project_id: int | None, status: str, only_from: str | None = None) -> None:
        """按 id 改写项目状态；only_from 限定当前状态，不匹配时静默跳过。"""
        if not project_id:
            return
        project = ProjectRepository().get_by_id(project_id)
        if project is None or (only_from is not None and project.status != only_from):
            return
        ProjectRepository().update_scenario(project_id, dict(project.scenario), status=status)
