from __future__ import annotations

import sqlite3
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
    from_json,
    invalidate_simulation_results,
    is_valid_json,
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
            repo.delete_for_project(project.id)
            self.assertIsNone(repo.latest_for_project(project.id))
            db.close()

    def test_delete_for_simulation_clears_rounds(self) -> None:
        """delete_for_simulation 清空指定仿真的全部轮次。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project = ProjectRepository(db).create("Demo", {})
            simulation = SimulationRepository(db).create(project.id)
            round_repo = SimulationRoundRepository(db)
            round_repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                state={},
            )

            round_repo.delete_for_simulation(simulation.id)

            self.assertEqual(round_repo.list_by_simulation(simulation.id), [])
            db.close()

    def test_invalidate_simulation_results(self) -> None:
        """作废主仿真：轮次/检查点/报告清空，项目状态回退 draft，仿真锚点保留。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project_repo = ProjectRepository(db)
            project = project_repo.create("Demo", {"industry": "electronics"})
            project_repo.update_scenario(project.id, {"industry": "electronics"}, status="completed")
            simulation = SimulationRepository(db).create(project.id)
            SimulationRoundRepository(db).save(
                project_id=project.id,
                simulation_id=simulation.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                state={},
            )
            ReportRepository(db).save(project_id=project.id, title="报告", markdown="md", summary={})
            CheckpointRepository(db).save(
                project_id=project.id, simulation_id=simulation.id,
                last_round=1, engine_state={},
            )

            invalidate_simulation_results(project.id, db)

            self.assertEqual(project_repo.get_by_id(project.id).status, "draft")
            self.assertIsNotNone(SimulationRepository(db).get_main(project.id))
            for table in ("simulation_rounds", "checkpoints", "reports"):
                row = db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                self.assertEqual(row[0], 0, f"{table} 应被清空")
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

    def test_migrate_upgrades_legacy_schema(self) -> None:
        """老库迁移：缺列补齐、废表清除，迁移后既有数据正常读写。"""
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "prism.db"
            conn = sqlite3.connect(str(db_file))
            conn.executescript(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    scenario_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL DEFAULT '主仿真',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL
                );
                INSERT INTO projects (name) VALUES ('旧项目');
                """
            )
            conn.commit()
            conn.close()

            db = Database(db_file)
            db.migrate()

            project = ProjectRepository(db).list_all()[0]
            self.assertEqual(project.name, "旧项目")
            self.assertIsNone(project.deleted_at)
            columns = {
                row["name"] for row in db.conn.execute("PRAGMA table_info(simulations)")
            }
            self.assertIn("scenario_json", columns)
            tables = {
                row["name"]
                for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            self.assertNotIn("agent_messages", tables)
            db.close()

    def test_project_recycle_bin(self) -> None:
        """软删除进回收站、可恢复；彻底删除经外键级联清空全部子表。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            project_repo = ProjectRepository(db)
            simulation_repo = SimulationRepository(db)
            round_repo = SimulationRoundRepository(db)
            report_repo = ReportRepository(db)
            checkpoint_repo = CheckpointRepository(db)
            knowledge_repo = KnowledgeRepository(db)

            project = project_repo.create("Demo", {"industry": "electronics"})
            simulation = simulation_repo.create(project.id)
            round_repo.save(
                project_id=project.id,
                simulation_id=simulation.id,
                round_index=1,
                simulated_hour=1,
                inventory_level=70.0,
                cost_index=55.0,
                delivery_delay=0.5,
                state={},
            )
            report_repo.save(project_id=project.id, title="报告", markdown="md", summary={})
            checkpoint_repo.save(
                project_id=project.id, simulation_id=simulation.id,
                last_round=1, engine_state={},
            )
            knowledge_repo.replace_for_project(
                project.id, [{"source": "a.md", "chunk_index": 0, "content": "原材料"}]
            )

            # 守卫：未进回收站的项目不能被彻底删除
            project_repo.hard_delete(project.id)
            self.assertIsNotNone(project_repo.get_by_id(project.id))

            project_repo.soft_delete(project.id)
            self.assertEqual(project_repo.list_all(), [])
            self.assertEqual([p.id for p in project_repo.list_deleted()], [project.id])

            project_repo.restore(project.id)
            self.assertEqual(project_repo.list_deleted(), [])
            self.assertEqual([p.id for p in project_repo.list_all()], [project.id])

            project_repo.soft_delete(project.id)
            project_repo.hard_delete(project.id)
            self.assertEqual(project_repo.list_deleted(), [])
            for table in (
                "simulations", "simulation_rounds",
                "checkpoints", "reports", "knowledge_chunks",
            ):
                row = db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                self.assertEqual(row[0], 0, f"{table} 应有零残留")
            db.close()

    def test_project_empty_trash(self) -> None:
        """empty_trash 清空全部已删项目，未删除项目不受影响。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            repo = ProjectRepository(db)

            keep = repo.create("保留", {})
            for name in ("甲", "乙"):
                repo.soft_delete(repo.create(name, {}).id)

            repo.empty_trash()
            self.assertEqual(repo.list_deleted(), [])
            self.assertEqual([p.id for p in repo.list_all()], [keep.id])
            db.close()

    def test_project_restore_all(self) -> None:
        """restore_all 恢复全部已删项目，未删除项目不受影响。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            repo = ProjectRepository(db)

            keep = repo.create("保留", {})
            for name in ("甲", "乙"):
                repo.soft_delete(repo.create(name, {}).id)

            repo.restore_all()
            self.assertEqual(repo.list_deleted(), [])
            self.assertEqual(len(repo.list_all()), 3)
            self.assertIsNotNone(repo.get_by_id(keep.id))
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


class JsonHelpersTests(unittest.TestCase):
    def test_from_json_corrupt_falls_back_to_default(self) -> None:
        """损坏的 JSON 文本降级为默认值而不是抛异常。"""
        self.assertEqual(from_json("{bad json", {}), {})
        self.assertEqual(from_json("", {"a": 1}), {"a": 1})
        self.assertEqual(from_json(None, []), [])
        self.assertEqual(from_json('{"k": 2}', {}), {"k": 2})

    def test_is_valid_json_detects_corruption(self) -> None:
        """is_valid_json 区分正常、空值与损坏文本，供 UI 标记数据异常。"""
        self.assertTrue(is_valid_json('{"k": 1}'))
        self.assertTrue(is_valid_json(""))
        self.assertTrue(is_valid_json(None))
        self.assertFalse(is_valid_json("{bad json"))

    def test_corrupt_scenario_json_detectable_on_project(self) -> None:
        """数据库中损坏的 scenario_json：scenario 降级为空 dict，且可被检测。"""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "prism.db")
            db.migrate()
            repo = ProjectRepository(db)
            project = repo.create("Demo", {"industry": "electronics"})
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE projects SET scenario_json = ? WHERE id = ?",
                    ("{corrupted", project.id),
                )

            broken = repo.get_by_id(project.id)
            self.assertEqual(broken.scenario, {})
            self.assertFalse(is_valid_json(broken.scenario_json))
            db.close()


if __name__ == "__main__":
    unittest.main()
