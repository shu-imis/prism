"""工作区子页面行为测试（事件/行为体/仿真/结果页）。"""
from __future__ import annotations

import unittest

from db.models import ProjectRepository, ReportRepository
from report.generator import SimulationReport
from tests.qt_helpers import QtDbTestCase
from ui.event_page import EventPage, NodeEditor
from ui.persona_page import PersonaPage
from ui.process_page import ProcessPage
from ui.result_page import ResultPage


class NodeEditorTests(QtDbTestCase):
    def test_last_node_cannot_be_removed(self) -> None:
        """仅剩一个节点时删除按钮禁用，且直接调 _remove 也被拒止。"""
        ed = self.track(NodeEditor())
        ed.add_node()
        self.assertFalse(ed._nodes[0]["remove"].isEnabled())
        ed._remove(ed._nodes[0]["card"])
        self.assertEqual(len(ed._nodes), 1)

        ed.add_node()
        self.assertTrue(all(nd["remove"].isEnabled() for nd in ed._nodes))
        ed._remove(ed._nodes[0]["card"])
        self.assertEqual(len(ed._nodes), 1)
        # 剩余节点重新编号为「节点 1」，删除入口重新禁用
        self.assertEqual(ed._nodes[0]["title"].text(), "节点 1")
        self.assertFalse(ed._nodes[0]["remove"].isEnabled())

    def test_get_nodes_uses_cost_index_key(self) -> None:
        """节点输出字段集固定，cost_index 原样带出。"""
        ed = self.track(NodeEditor())
        ed.add_node({"name": "节点", "cost_index": 33})
        nodes = ed.get_nodes()
        self.assertEqual(nodes[0]["cost_index"], 33)
        self.assertEqual(set(nodes[0]), {
            "name", "type", "inventory", "lead_time",
            "capacity", "cost_index", "upstream", "downstream",
        })


class EventPageTests(QtDbTestCase):
    def test_number_inputs_parse_defaults(self) -> None:
        """整型参数的默认值必须能被 NumberInput 解析（float 字符串会静默回落到最小值）。"""
        page = self.track(EventPage())
        self.assertEqual(page._inv.value(), 75)
        self.assertEqual(page._cost.value(), 50)
        self.assertAlmostEqual(page._svc.value(), 0.85)

    def test_save_rejects_empty_title(self) -> None:
        """空标题不允许创建项目。"""
        page = self.track(EventPage())
        errors: list[str] = []
        page.log = lambda msg, is_error=False: errors.append(msg) if is_error else None
        fired: list[int] = []
        page.project_saved.connect(fired.append)

        page._bg.setPlainText("背景")
        page._save()
        self.assertEqual(fired, [])
        self.assertTrue(errors)
        self.assertIsNone(page._pid)

    def test_save_writes_back_project_name(self) -> None:
        """改名保存时项目名同步回写。"""
        repo = ProjectRepository()
        p = repo.create("旧名", {"background": "背景"})
        page = self.track(EventPage())
        page.load_project(p.id)

        page._title.setText("新名")
        page._save()
        project = repo.get_by_id(p.id)
        self.assertEqual(project.name, "新名")
        self.assertEqual(project.scenario["title"], "新名")

    def test_save_creates_project_for_new_page(self) -> None:
        """新建项目首次保存以表单内容建库并广播项目 id。"""
        page = self.track(EventPage())
        fired: list[int] = []
        page.project_saved.connect(fired.append)

        page._title.setText("新建项目")
        page._bg.setPlainText("背景")
        page._save()

        projects = ProjectRepository().list_all()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, "新建项目")
        self.assertEqual(projects[0].scenario["background"], "背景")
        self.assertEqual(fired, [projects[0].id])
        self.assertEqual(page._pid, projects[0].id)

    def test_reset_clears_industry_and_restores_defaults(self) -> None:
        """reset 清空行业输入并恢复参数默认值。"""
        page = self.track(EventPage())
        page._industry.setText("电子制造")
        page._inv.setValue(10)
        page.reset()
        self.assertEqual(page._industry.text(), "")
        self.assertEqual(page._inv.value(), 75)
        self.assertEqual(page._cost.value(), 50)

    def test_docs_imported_result_dropped_after_project_switch(self) -> None:
        """导入完成回调的 pid 与当前项目不符时丢弃结果。"""
        page = self.track(EventPage())
        page._pid = 999  # 等待导入期间已切换到其他项目
        page._on_docs_imported(["旧项目文档"], pid=None)
        self.assertEqual(page._imported, [])


class PersonaPageTests(QtDbTestCase):
    def test_save_logs_error_when_project_deleted(self) -> None:
        """项目已删除时保存不静默：记录错误日志且不崩溃。"""
        repo = ProjectRepository()
        p = repo.create("示例", {"background": "背景"})
        page = self.track(PersonaPage())
        errors: list[str] = []
        page.log = lambda msg, is_error=False: errors.append(msg) if is_error else None
        page.load_project(p.id)

        repo.soft_delete(p.id)
        fired: list[int] = []
        page.agents_saved.connect(fired.append)
        page._save()
        self.assertEqual(fired, [])
        self.assertTrue(errors)


class ProcessPageWorkerTests(QtDbTestCase):
    def test_iter_ai_workers_merges_subpages(self) -> None:
        """iter_ai_workers 合并各子页面的 _ai_workers，供关窗兜底。"""
        page = self.track(ProcessPage())
        self.assertEqual(page.iter_ai_workers(), [])
        sentinel = object()
        page._ep._ai_workers = [sentinel]
        self.assertEqual(page.iter_ai_workers(), [sentinel])


class ResultPageTests(QtDbTestCase):
    def test_banner_meta_has_no_leading_separator(self) -> None:
        """项目名为空时横幅 meta 不残留前导分隔符。"""
        page = self.track(ResultPage())
        report = SimulationReport(project_name="", scenario_background="")
        page._render_banner(report)
        text = page._banner_project.text()
        self.assertTrue(text)
        self.assertFalse(text.startswith("　"))
        self.assertFalse(text.startswith("·"))

    def test_load_project_fills_missing_project_name(self) -> None:
        """旧报告未存项目名时，横幅以当前项目名补齐。"""
        repo = ProjectRepository()
        p = repo.create("演示供应链", {"background": "背景"})
        report = SimulationReport(project_name="", scenario_background="背景")
        ReportRepository().save_or_update_latest(
            project_id=p.id,
            title="报告",
            markdown="# 报告",
            summary=report.to_dict(),
        )
        page = self.track(ResultPage())
        page.load_project(p.id)
        self.assertTrue(page._banner_project.text().startswith("演示供应链"))


if __name__ == "__main__":
    unittest.main()
