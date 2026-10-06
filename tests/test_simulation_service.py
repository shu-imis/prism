"""仿真服务测试：启动准备、状态收尾、历史装载与执行单元。"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core.simulation_engine import SimulationEngine, SimulationRecoverableError
from db.database import Database
from db.models import (
    CheckpointRepository,
    ProjectRepository,
    SimulationRepository,
    SimulationRoundRepository,
)
from llm.client import LLMClient, LLMVendor, VendorSettings
from services.simulation import SimulationRun, SimulationService
from tests.helpers import make_fake_llm_client, make_json_client


class SimulationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Database(Path(self._tmp.name) / "test.db")
        Database._default_instance = self._db
        self._db.migrate()
        self._svc = SimulationService()
        self._repo = ProjectRepository()

    def tearDown(self) -> None:
        self._db.close()
        Database._default_instance = None
        self._tmp.cleanup()

    def _make_project(self, status: str = "draft") -> int:
        project = self._repo.create("演示供应链", {"background": "背景"})
        self._repo.update_scenario(project.id, dict(project.scenario), status=status)
        return project.id

    def _add_rounds(self, pid: int, *levels: float) -> int:
        sim = SimulationRepository().get_or_create_main(pid)
        for index, level in enumerate(levels, start=1):
            SimulationRoundRepository().save(
                project_id=pid,
                simulation_id=sim.id,
                round_index=index,
                simulated_hour=index,
                inventory_level=level,
                cost_index=55.0,
                delivery_delay=0.5,
                state={},
            )
        return sim.id

    def test_prepare_start_without_llm_keeps_state(self) -> None:
        """未配置 Key：返回空且项目状态与轮次保持原样。"""
        pid = self._make_project(status="completed")
        sim_id = self._add_rounds(pid, 70.0)

        with mock.patch("services.simulation.build_llm_client", return_value=None):
            llm, checkpoint = self._svc.prepare_start(pid)

        self.assertIsNone(llm)
        self.assertIsNone(checkpoint)
        self.assertEqual(self._repo.get_by_id(pid).status, "completed")
        self.assertEqual(len(SimulationRoundRepository().list_by_simulation(sim_id)), 1)

    def test_prepare_start_clears_stale_rounds_without_checkpoint(self) -> None:
        """无断点：清空上次残留轮次并把项目置为运行中。"""
        pid = self._make_project()
        sim_id = self._add_rounds(pid, 70.0, 65.0)
        client = make_fake_llm_client()

        with mock.patch("services.simulation.build_llm_client", return_value=client):
            llm, checkpoint = self._svc.prepare_start(pid)

        self.assertIs(llm, client)
        self.assertIsNone(checkpoint)
        self.assertEqual(SimulationRoundRepository().list_by_simulation(sim_id), [])
        self.assertEqual(self._repo.get_by_id(pid).status, "running")

    def test_prepare_start_keeps_rounds_with_checkpoint(self) -> None:
        """有断点：轮次保留，断点随返回值带出。"""
        pid = self._make_project(status="interrupted")
        sim_id = self._add_rounds(pid, 70.0)
        checkpoint_id = CheckpointRepository().save(
            project_id=pid, simulation_id=sim_id, last_round=1, engine_state={}
        )

        with mock.patch(
            "services.simulation.build_llm_client", return_value=make_fake_llm_client()
        ):
            _, checkpoint = self._svc.prepare_start(pid)

        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint.id, checkpoint_id)
        self.assertEqual(len(SimulationRoundRepository().list_by_simulation(sim_id)), 1)

    def test_status_marks(self) -> None:
        """收尾状态：completed / interrupted 直写，草稿回退只从 running 生效。"""
        pid = self._make_project()
        self._svc.finish_success(pid)
        self.assertEqual(self._repo.get_by_id(pid).status, "completed")

        self._svc.mark_interrupted(pid)
        self.assertEqual(self._repo.get_by_id(pid).status, "interrupted")

        self._svc.mark_draft(pid)
        self.assertEqual(self._repo.get_by_id(pid).status, "interrupted")

        project = self._repo.get_by_id(pid)
        self._repo.update_scenario(pid, dict(project.scenario), status="running")
        self._svc.mark_draft(pid)
        self.assertEqual(self._repo.get_by_id(pid).status, "draft")

    def test_load_history_returns_rounds_checkpoint_and_status(self) -> None:
        """历史装载：轮次按序返回，断点有无与项目状态一并带出。"""
        pid = self._make_project(status="completed")
        sim_id = self._add_rounds(pid, 70.0, 65.0)

        history = self._svc.load_history(pid)
        self.assertEqual([r.inventory_level for r in history.rounds], [70.0, 65.0])
        self.assertFalse(history.has_checkpoint)
        self.assertEqual(history.status, "completed")

        CheckpointRepository().save(
            project_id=pid, simulation_id=sim_id, last_round=2, engine_state={}
        )
        self.assertTrue(self._svc.load_history(pid).has_checkpoint)


class SimulationRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db = Database(Path(self._tmp.name) / "test.db")
        Database._default_instance = self._db
        self._db.migrate()

    def tearDown(self) -> None:
        self._db.close()
        Database._default_instance = None
        self._tmp.cleanup()

    def test_run_persists_rounds_and_builds_report(self) -> None:
        """执行单元：场景装载 → 单轮仿真落库 → 报告生成（AI 失败自动降级）。"""
        project = ProjectRepository().create("演示供应链", {"background": "测试背景"})
        client = make_fake_llm_client()
        engine = SimulationEngine(client, random_seed=7)
        run = SimulationRun(project.id, client, 1, engine)

        with mock.patch("services.simulation.DB_PATH", self._db.db_path):
            results = run.run()
            report = run.build_report(results)

        self.assertEqual(len(results), 2)
        self.assertEqual(report.project_name, "演示供应链")
        self.assertEqual(report.final_inventory, results[-1].inventory_level)
        self.assertEqual(report.ai_analysis, {})
        sim = SimulationRepository().get_main(project.id)
        self.assertEqual(len(SimulationRoundRepository().list_by_simulation(sim.id)), 2)

    def test_run_discards_checkpoint_on_fatal_error(self) -> None:
        """线程内致命失败：清除断点，避免反复恢复到同一错误。"""
        project = ProjectRepository().create("演示供应链", {"background": "测试背景"})
        client = make_json_client("boom")
        engine = SimulationEngine(client, random_seed=7)
        run = SimulationRun(project.id, client, 1, engine)
        errors: list[Exception] = []

        def drive():
            # 与生产一致地在工作线程内执行：清理必须使用线程内自建连接
            with mock.patch("services.simulation.DB_PATH", self._db.db_path):
                try:
                    run.run()
                except Exception as exc:  # 线程内异常带出供断言
                    errors.append(exc)

        thread = threading.Thread(target=drive)
        thread.start()
        thread.join()

        self.assertEqual([type(e) for e in errors], [RuntimeError])
        self.assertIsNone(CheckpointRepository().latest_for_project(project.id))

    def test_run_keeps_checkpoint_on_recoverable_error(self) -> None:
        """后续轮次集体失败属可恢复：断点保留，供从断点续跑。"""
        project = ProjectRepository().create("演示供应链", {"background": "测试背景"})
        action = (
            '{"inventory_change": 1, "cost_change": 1, "delay_change": 0.1, '
            '"service_change": 0.01, "margin_change": 0.01, '
            '"pressure_change": 0.0, "risk_description": "", '
            '"response_summary": "正常运作", "decision_shift": "none"}'
        )

        def transport(vendor, messages, options):
            # 首轮（周期 0）全部成功；次轮集体故障
            if "第 0 个周期" in messages[0]["content"]:
                return action
            raise RuntimeError("次轮集体故障")

        client = LLMClient(
            vendors=[VendorSettings(LLMVendor.OPENAI, "gpt-5.6-sol", "key")],
            max_retries=0,
            transport=transport,
        )
        engine = SimulationEngine(client, random_seed=7)
        run = SimulationRun(project.id, client, 2, engine)

        with mock.patch("services.simulation.DB_PATH", self._db.db_path):
            with self.assertRaises(SimulationRecoverableError):
                run.run()

        self.assertIsNotNone(CheckpointRepository().latest_for_project(project.id))


if __name__ == "__main__":
    unittest.main()
