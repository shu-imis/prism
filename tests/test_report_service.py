"""报告服务测试：结果装载、缺失重生成与持久化。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.world_state import WorldState
from db.database import Database
from db.models import (
    ProjectRepository,
    ReportRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from report.generator import SimulationReport
from services.reports import ReportService


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Database(Path(self._tmp.name) / "test.db")
        Database._default_instance = self._db
        self._db.migrate()
        self._svc = ReportService()
        self._project = ProjectRepository().create("演示供应链", {"background": "背景"})

    def tearDown(self) -> None:
        self._db.close()
        Database._default_instance = None
        self._tmp.cleanup()

    def _add_rounds(self, *levels: float) -> None:
        sim = SimulationRepository().get_or_create_main(self._project.id)
        for index, level in enumerate(levels, start=1):
            state = WorldState(round=index, simulated_hour=index, inventory_level=level)
            SimulationRoundRepository().save(
                project_id=self._project.id,
                simulation_id=sim.id,
                round_index=index,
                simulated_hour=index,
                inventory_level=level,
                cost_index=55.0,
                delivery_delay=0.5,
                state=state.to_dict(),
            )

    def test_load_result_without_data(self) -> None:
        """无报告无轮次：报告为 None，轮次为空。"""
        report, rounds = self._svc.load_result(self._project.id)
        self.assertIsNone(report)
        self.assertEqual(rounds, [])

    def test_load_result_reads_persisted_report_and_rounds(self) -> None:
        """报告已落库：按 summary 还原，轮次一并读回。"""
        self._add_rounds(70.0, 65.0)
        saved = SimulationReport(
            project_name="演示供应链", scenario_background="背景", final_inventory=65.0
        )
        ReportRepository().save_or_update_latest(
            project_id=self._project.id, title="报告", markdown="# 报告", summary=saved.to_dict()
        )

        report, rounds = self._svc.load_result(self._project.id)
        self.assertEqual(report.project_name, "演示供应链")
        self.assertEqual(report.final_inventory, 65.0)
        self.assertEqual([r.inventory_level for r in rounds], [70.0, 65.0])

    def test_load_result_generates_missing_report_without_saving(self) -> None:
        """报告缺失但有轮次：现场生成，不落库。"""
        self._add_rounds(70.0, 60.0)
        report, rounds = self._svc.load_result(self._project.id)
        self.assertIsNotNone(report)
        self.assertEqual(report.project_name, "演示供应链")
        self.assertEqual(len(rounds), 2)
        self.assertFalse(ReportRepository().list_by_project(self._project.id))

    def test_load_result_falls_back_on_corrupt_round_state(self) -> None:
        """轮次 state 缺必填键：按行内指标还原，不中断装载。"""
        sim = SimulationRepository().get_or_create_main(self._project.id)
        SimulationRoundRepository().save(
            project_id=self._project.id,
            simulation_id=sim.id,
            round_index=1,
            simulated_hour=3,
            inventory_level=42.0,
            cost_index=60.0,
            delivery_delay=1.5,
            state={},
        )

        _, rounds = self._svc.load_result(self._project.id)
        self.assertEqual(rounds[0].round, 1)
        self.assertEqual(rounds[0].simulated_hour, 3)
        self.assertEqual(rounds[0].inventory_level, 42.0)

    def test_persist_inserts_then_updates_latest(self) -> None:
        """持久化：首次插入，再次调用更新同一份报告。"""
        report = SimulationReport(project_name="演示供应链", scenario_background="背景")
        rounds = [WorldState(round=1, simulated_hour=1, inventory_level=70.0)]
        self._svc.persist(self._project.id, report, rounds)

        records = ReportRepository().list_by_project(self._project.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "演示供应链 - 供应链演化仿真报告")
        self.assertIn("## 指标演化数据", records[0].markdown)
        report_id = records[0].id

        report.ai_analysis = {"evolution_analysis": "分析"}
        self._svc.persist(self._project.id, report, rounds)

        records = ReportRepository().list_by_project(self._project.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, report_id)
        self.assertEqual(records[0].summary["ai_analysis"]["evolution_analysis"], "分析")


if __name__ == "__main__":
    unittest.main()
