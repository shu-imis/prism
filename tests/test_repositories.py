from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
    CheckpointRepository,
    KnowledgeRepository,
)


class RepositoryTests(unittest.TestCase):
    def test_database_repositories_round_trip(self) -> None:
        """验证 Project/Simulation/SimulationRound/Report 四个 Repository 的增删改查。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()

            project_repo = ProjectRepository(db)
            simulation_repo = SimulationRepository(db)
            round_repo = SimulationRoundRepository(db)
            report_repo = ReportRepository(db)

            project = project_repo.create("Demo", {"industry": "electronics"})
            project = project_repo.update_scenario(
                project.id,
                {"title": "电子产品供应链", "industry": "electronics", "initial_inventory": 80},
                name="电子产品供应链",
            )
            self.assertEqual(project.name, "电子产品供应链")
            self.assertEqual(project.scenario["industry"], "electronics")
            simulation = simulation_repo.create(project.id)

            saved_round = round_repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                service_level=0.82,
                profit_margin=0.12,
                resilience_score=58.0,
                state={"key_events": ["需求激增"]},
                agent_messages=[
                    {
                        "agent_name": "零售商",
                        "decision_stance": "aggressive",
                        "content": "启动促销活动。",
                    }
                ],
            )
            updated_round = round_repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=65.0,
                cost_index=58.0,
                delivery_delay=0.8,
                service_level=0.80,
                profit_margin=0.10,
                resilience_score=55.0,
                state={"key_events": ["需求激增"]},
            )

            self.assertEqual(saved_round.id, updated_round.id)
            self.assertEqual(round_repo.list_by_simulation(simulation.id)[0].inventory_level, 65.0)

            report_id = report_repo.save(
                project_id=project.id,
                title="Demo 报告",
                markdown="# Demo",
                summary={"result": "demo"},
            )
            self.assertEqual(report_repo.list_by_project(project.id)[0].id, report_id)
            db.close()

    def test_knowledge_repository_replace_and_search(self) -> None:
        """验证知识库片段的替换和关键词搜索。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            repo = KnowledgeRepository(db)

            repo.replace_for_project(
                project.id,
                [
                    {"source": "a.md", "chunk_index": 0, "content": "原材料 价格 波动 供应商 产能"},
                    {"source": "b.md", "chunk_index": 0, "content": "物流 运输 仓储 配送"},
                ],
            )
            hits = repo.search(project.id, "原材料价格供应商产能", limit=1)

            self.assertEqual(len(repo.list_by_project(project.id)), 2)
            self.assertEqual(hits[0].source, "a.md")

            # 空列表替换 = 清空知识库（设置页/Step1 清空入口依赖此语义）
            repo.replace_for_project(project.id, [])
            self.assertEqual(repo.list_by_project(project.id), [])
            db.close()

    def test_checkpoint_repository_round_trip(self) -> None:
        """验证仿真检查点的保存、读取、删除。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            simulation = SimulationRepository(db).create(project.id)
            repo = CheckpointRepository(db)

            checkpoint_id = repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                last_round=2,
                engine_state={"simulation_index": 0, "last_round": 2},
            )
            latest = repo.latest_for_project(project.id)

            self.assertIsNotNone(latest)
            self.assertEqual(latest.id, checkpoint_id)
            self.assertEqual(latest.engine_state["last_round"], 2)
            self.assertEqual(len(repo.list_unfinished()), 1)
            repo.delete_for_project(project.id)
            self.assertIsNone(repo.latest_for_project(project.id))
            db.close()

    def test_report_repository_delete_for_project(self) -> None:
        """验证 ReportRepository.delete_for_project 删除项目全部报告。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {"industry": "electronics"})
            report_repo = ReportRepository(db)

            report_repo.save(project_id=project.id, title="报告", markdown="md", summary={})
            self.assertEqual(len(report_repo.list_by_project(project.id)), 1)

            report_repo.delete_for_project(project.id)
            self.assertEqual(report_repo.list_by_project(project.id), [])
            db.close()

    def test_database_sets_busy_timeout(self) -> None:
        """验证连接设置 busy_timeout，避免双连接并发写时默认 5s 导致 SQLITE_BUSY。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            row = db.conn.execute("PRAGMA busy_timeout").fetchone()
            self.assertEqual(row[0], 30000)
            db.close()

    def test_report_save_or_update_latest(self) -> None:
        """save_or_update_latest：首次插入，再次调用更新同一行，reports 表不膨胀。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {})
            repo = ReportRepository(db)

            first_id = repo.save_or_update_latest(
                project_id=project.id, title="报告", markdown="v1", summary={"n": 1}
            )
            second_id = repo.save_or_update_latest(
                project_id=project.id, title="报告", markdown="v2",
                summary={"n": 2, "ai_analysis": {"evolution_analysis": "x"}},
            )

            self.assertEqual(first_id, second_id)
            reports = repo.list_by_project(project.id)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].markdown, "v2")
            self.assertEqual(reports[0].summary["n"], 2)
            db.close()


if __name__ == "__main__":
    unittest.main()
