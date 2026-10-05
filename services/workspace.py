"""工作区服务：项目列表、装载自愈、保存与知识库。

页面通过本模块访问项目数据，不直触 Repository。
"""
from __future__ import annotations

from core.document_importer import ImportedDocument, chunk_text
from db.models import (
    CheckpointRepository,
    KnowledgeChunk,
    KnowledgeRepository,
    Project,
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
    invalidate_simulation_results,
)


class WorkspaceService:
    """项目数据操作的服务入口。"""

    # --- 项目列表 / 回收站 ---

    def list_active(self) -> list[Project]:
        return ProjectRepository().list_all()

    def list_deleted(self) -> list[Project]:
        return ProjectRepository().list_deleted()

    def soft_delete(self, project_id: int) -> None:
        ProjectRepository().soft_delete(project_id)

    def restore(self, project_id: int) -> None:
        ProjectRepository().restore(project_id)

    def restore_all(self) -> None:
        ProjectRepository().restore_all()

    def hard_delete(self, project_id: int) -> None:
        ProjectRepository().hard_delete(project_id)

    def empty_trash(self) -> None:
        ProjectRepository().empty_trash()

    # --- 装载 ---

    def load_project(self, project_id: int | None) -> Project | None:
        """读取单个项目；不存在或已删除返回 None。"""
        if project_id is None:
            return None
        return ProjectRepository().get_by_id(project_id)

    def load_workspace(self, project_id: int) -> Project | None:
        """装载工作区项目并自愈陈旧状态。

        running 是重启前的残留：有检查点=中断（可断点恢复），
        无检查点但有轮次/报告数据=已跑完，否则回到草稿；
        interrupted 且检查点已丢失时同样回退草稿。
        """
        project = ProjectRepository().get_by_id(project_id)
        if project is None:
            return None
        if project.status == "running":
            has_checkpoint = bool(CheckpointRepository().latest_for_project(project_id))
            has_reports = bool(ReportRepository().list_by_project(project_id))
            has_data = has_reports or self._has_rounds(project_id)
            if has_checkpoint:
                status = "interrupted"
            else:
                status = "completed" if has_data else "draft"
            return ProjectRepository().update_scenario(
                project_id, dict(project.scenario), status=status
            )
        if project.status == "interrupted":
            if not CheckpointRepository().latest_for_project(project_id):
                return ProjectRepository().update_scenario(
                    project_id, dict(project.scenario), status="draft"
                )
        return project

    def status(self, project_id: int) -> str | None:
        """项目当前状态；不存在返回 None。"""
        project = ProjectRepository().get_by_id(project_id)
        return project.status if project else None

    # --- 保存 ---

    def create_project(self, name: str, scenario: dict) -> Project:
        """以表单内容新建项目。"""
        return ProjectRepository().create(name, scenario)

    def commit_save(
        self,
        project_id: int,
        fields: dict,
        *,
        name: str | None = None,
        invalidate: bool = False,
    ) -> Project:
        """把本步字段合并进项目场景后落库；invalidate 为真时先作废旧仿真结果。"""
        project = ProjectRepository().get_by_id(project_id)
        if project is None:
            raise KeyError(f"项目不存在: {project_id}")
        if invalidate:
            invalidate_simulation_results(project_id)
        scenario = dict(project.scenario)
        scenario.update(fields)
        return ProjectRepository().update_scenario(project_id, scenario, name=name)

    # --- 知识库 ---

    def knowledge_chunks(self, project_id: int) -> list[KnowledgeChunk]:
        return KnowledgeRepository().list_by_project(project_id)

    def replace_knowledge_from_docs(self, project_id: int, docs: list[ImportedDocument]) -> None:
        """把导入文档分块后整体写入项目知识库。"""
        entries = [
            {"source": d.path, "chunk_index": i, "content": c}
            for d in docs
            for i, c in enumerate(chunk_text(d.text))
        ]
        KnowledgeRepository().replace_for_project(project_id, entries)

    def clear_knowledge(self, project_id: int) -> None:
        KnowledgeRepository().replace_for_project(project_id, [])

    # --- 内部 ---

    @staticmethod
    def _has_rounds(project_id: int) -> bool:
        main = SimulationRepository().get_main(project_id)
        return bool(main and SimulationRoundRepository().list_by_simulation(main.id))
