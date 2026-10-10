"""工作区服务测试：新建首存、失效保存与装载自愈。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.document_importer import ImportedDocument
from db.database import Database
from db.models import (
    CheckpointRepository,
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from services.workspace import WorkspaceService


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Database(Path(self._tmp.name) / "test.db")
        Database._default_instance = self._db
        self._db.migrate()
        self._svc = WorkspaceService()

    def tearDown(self) -> None:
        self._db.close()
        Database._default_instance = None
        self._tmp.cleanup()

    def test_create_project_persists_scenario(self) -> None:
        """新建首存：表单内容建库后可按 id 读回。"""
        form = {"title": "新项目", "background": "背景", "initial_inventory": 70}
        project = self._svc.create_project("新项目", form)

        loaded = self._svc.load_project(project.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "新项目")
        self.assertEqual(loaded.scenario["background"], "背景")
        self.assertEqual(loaded.status, "draft")

    def test_commit_save_merges_fields(self) -> None:
        """常规保存：字段并入既有场景，未触碰的配置保留，名称同步回写。"""
        project = ProjectRepository().create("示例", {"agents_config": {"1": {}}})
        saved = self._svc.commit_save(project.id, {"background": "新背景"}, name="新名字")
        self.assertEqual(saved.name, "新名字")
        self.assertEqual(saved.scenario["background"], "新背景")
        self.assertEqual(saved.scenario["agents_config"], {"1": {}})

    def test_commit_save_invalidates_results(self) -> None:
        """失效保存：清空轮次/检查点/报告并回退草稿，场景照常更新。"""
        repo = ProjectRepository()
        project = repo.create("示例", {"background": "旧"})
        sim = SimulationRepository().create(project.id)
        SimulationRoundRepository().save(
            project_id=project.id,
            simulation_id=sim.id,
            round_index=1,
            simulated_hour=1,
            inventory_level=70.0,
            cost_index=55.0,
            delivery_delay=0.5,
            state={},
        )
        CheckpointRepository().save(
            project_id=project.id, simulation_id=sim.id, last_round=1, engine_state={}
        )
        ReportRepository().save(
            project_id=project.id, title="报告", markdown="# 报告", summary={}
        )
        repo.update_scenario(project.id, dict(project.scenario), status="completed")

        saved = self._svc.commit_save(project.id, {"background": "新"}, invalidate=True)

        self.assertEqual(saved.scenario["background"], "新")
        self.assertEqual(saved.status, "draft")
        self.assertFalse(SimulationRoundRepository().list_by_simulation(sim.id))
        self.assertIsNone(CheckpointRepository().latest_for_project(project.id))
        self.assertFalse(ReportRepository().list_by_project(project.id))

    def test_replace_knowledge_from_docs_stores_chunks(self) -> None:
        """导入文档按 source/chunk_index/content 形状分块写入知识库。"""
        project = self._svc.create_project("示例", {})
        docs = [
            ImportedDocument(path="a.md", title="甲", text="供应波动。" * 300),
            ImportedDocument(path="b.md", title="乙", text="物流延迟。"),
        ]
        self._svc.replace_knowledge_from_docs(project.id, docs)
        chunks = self._svc.knowledge_chunks(project.id)
        self.assertEqual({c.source for c in chunks}, {"a.md", "b.md"})
        self.assertTrue(all(c.content for c in chunks))
        for source in ("a.md", "b.md"):
            indices = sorted(c.chunk_index for c in chunks if c.source == source)
            self.assertEqual(indices, list(range(len(indices))))

    def test_load_missing_project_returns_none(self) -> None:
        """不存在的项目：读取与状态查询返回 None。"""
        self.assertIsNone(self._svc.load_project(9999))
        self.assertIsNone(self._svc.load_workspace(9999))
        self.assertIsNone(self._svc.status(9999))

    def test_load_workspace_heals_stale_status(self) -> None:
        """装载自愈矩阵：running 按检查点/数据判定，interrupted 无检查点回退草稿。"""
        repo = ProjectRepository()
        sim_repo = SimulationRepository()
        round_repo = SimulationRoundRepository()
        cp_repo = CheckpointRepository()
        report_repo = ReportRepository()

        def make(status: str) -> int:
            project = repo.create("示例", {})
            repo.update_scenario(project.id, dict(project.scenario), status=status)
            return project.id

        def add_round(pid: int) -> None:
            sim = sim_repo.get_or_create_main(pid)
            round_repo.save(
                project_id=pid,
                simulation_id=sim.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                state={},
            )

        def add_checkpoint(pid: int) -> None:
            sim = sim_repo.get_or_create_main(pid)
            cp_repo.save(project_id=pid, simulation_id=sim.id, last_round=1, engine_state={})

        # running 有检查点：判为中断
        pid = make("running")
        add_checkpoint(pid)
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "interrupted")

        # running 无检查点但有轮次：判为已跑完
        pid = make("running")
        add_round(pid)
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "completed")

        # running 无检查点但有报告：同样判为已跑完
        pid = make("running")
        report_repo.save(project_id=pid, title="报告", markdown="#", summary={})
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "completed")

        # running 无检查点无数据：回到草稿
        pid = make("running")
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "draft")

        # interrupted 无检查点：回退草稿
        pid = make("interrupted")
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "draft")

        # interrupted 有检查点：保持中断
        pid = make("interrupted")
        add_checkpoint(pid)
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "interrupted")

        # completed：不受装载影响
        pid = make("completed")
        self._svc.load_workspace(pid)
        self.assertEqual(self._svc.status(pid), "completed")


if __name__ == "__main__":
    unittest.main()
