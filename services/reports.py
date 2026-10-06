"""报告服务：结果装载与报告持久化。

页面通过本模块读写报告与仿真轮次，不直触 Repository。
"""
from __future__ import annotations

from core.world_state import WorldState
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from report.exporter import ReportExporter
from report.generator import ReportGenerator, SimulationReport


class ReportService:
    """结果报告装载与落库的服务入口。"""

    def load_result(self, project_id: int) -> tuple[SimulationReport | None, list[WorldState]]:
        """装载项目的结果报告与仿真轮次。

        报告缺失但有轮次数据时按轮次现场生成，不落库；报告中项目名
        为空时以当前项目名补齐，避免横幅只剩日期。
        """
        rounds = self._load_rounds(project_id)
        project = ProjectRepository().get_by_id(project_id)
        project_name = project.name if project else ""

        reports = ReportRepository().list_by_project(project_id)
        if reports:
            report = SimulationReport.from_dict(reports[0].summary)
            if not report.project_name:
                report.project_name = project_name
        elif rounds:
            generator = ReportGenerator(project_name)
            generator.set_simulation_result(rounds)
            report = generator.generate()
        else:
            report = None
        return report, rounds

    def persist(self, project_id: int, report: SimulationReport, rounds: list[WorldState]) -> None:
        """更新项目主报告，无则插入；标题、Markdown 与摘要一并写入。"""
        ReportRepository().save_or_update_latest(
            project_id=project_id,
            title=f"{report.project_name} - 供应链演化仿真报告",
            markdown=ReportExporter.to_markdown(report, rounds),
            summary=report.to_dict(),
        )

    # --- 内部 ---

    @staticmethod
    def _load_rounds(project_id: int) -> list[WorldState]:
        """读取项目主仿真的轮次状态；无仿真返回空列表。"""
        main = SimulationRepository().get_main(project_id)
        if main is None:
            return []
        states = []
        for record in SimulationRoundRepository().list_by_simulation(main.id):
            try:
                state = WorldState.from_dict(record.state)
            except Exception:
                state = WorldState(
                    round=record.round_index,
                    simulated_hour=record.simulated_hour,
                    inventory_level=record.inventory_level,
                    cost_index=record.cost_index,
                    delivery_delay=record.delivery_delay,
                    service_level=record.service_level,
                    profit_margin=record.profit_margin,
                    resilience_score=record.resilience_score,
                )
            states.append(state)
        return states
