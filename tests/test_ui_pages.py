"""UI 页面行为测试：主窗口导航与项目页（项目列表 / 回收站）。"""
from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtCore import QPoint, QEvent
from PySide6.QtWidgets import QPushButton

from db.models import ProjectRepository
from tests.qt_helpers import QtDbTestCase, app as _app
from ui.main_window import MainWindow
from ui.projects_page import ProjectsPage
from ui.widgets import PopupMenu


class MainWindowRoutingTests(QtDbTestCase):
    def test_sidebar_routing(self) -> None:
        """侧栏四项 → stack 索引与项目页模式：列表/回收站共用项目页。"""
        w = self.track(MainWindow())
        w._go(0)
        self.assertEqual((w._stack.currentIndex(), w._projects._mode), (0, "active"))
        w._go(1)
        self.assertEqual(w._stack.currentIndex(), 1)
        w._go(2)
        self.assertEqual((w._stack.currentIndex(), w._projects._mode), (0, "trash"))
        self.assertTrue(w._btns[2].isChecked())
        w._go(3)
        self.assertEqual(w._stack.currentIndex(), 2)


class MainWindowSignalRoutingTests(QtDbTestCase):
    """信号接线回归：项目页信号必须路由到工作区（stack 1），回收站是 _go(2)。"""

    def test_new_project_signal_goes_to_workspace(self) -> None:
        w = self.track(MainWindow())
        w._projects.new_project.emit()
        self.assertEqual(w._stack.currentIndex(), 1)
        self.assertEqual(w._projects._mode, "active")

    def test_open_project_signal_goes_to_workspace(self) -> None:
        pid = ProjectRepository().create("示例", {}).id
        w = self.track(MainWindow())
        w._projects.open_project.emit(pid)
        self.assertEqual(w._stack.currentIndex(), 1)
        self.assertEqual(w._projects._mode, "active")
        self.assertEqual(w._process._pid, pid)

    def test_open_project_from_trash_mode_goes_to_workspace(self) -> None:
        pid = ProjectRepository().create("示例", {}).id
        w = self.track(MainWindow())
        w._go(2)  # 回收站
        w._projects.open_project.emit(pid)
        self.assertEqual(w._stack.currentIndex(), 1)
        # 工作区导航不改写项目页模式
        self.assertEqual(w._projects._mode, "trash")

    def test_deleting_open_project_resets_workspace(self) -> None:
        """删除工作区当前项目 → 工作区重置并离开工作区页；删其他项目不影响。"""
        repo = ProjectRepository()
        pid = repo.create("示例", {}).id
        other = repo.create("其他", {}).id
        w = self.track(MainWindow())
        w._projects.open_project.emit(pid)
        w._projects.project_deleted.emit(other)
        self.assertEqual(w._process._pid, pid)
        w._projects.project_deleted.emit(pid)
        self.assertIsNone(w._process._pid)
        self.assertEqual(w._stack.currentIndex(), 0)

    def test_delete_actions_emit_project_deleted(self) -> None:
        """软删 / 彻底删除 / 清空回收站三条路径均发出 project_deleted。"""
        repo = ProjectRepository()
        pid = repo.create("示例", {}).id
        page = self.track(ProjectsPage())
        fired: list[int] = []
        page.project_deleted.connect(fired.append)
        with mock.patch("ui.projects_page.ConfirmDialog.confirm", return_value=True):
            page._confirm_delete(pid, "示例")
            page._confirm_hard_delete(pid, "示例")
        self.assertEqual(fired, [pid, pid])

        # 清空回收站：按回收站中的项目逐个发出
        p1 = repo.create("甲", {}).id
        p2 = repo.create("乙", {}).id
        repo.soft_delete(p1)
        repo.soft_delete(p2)
        fired.clear()
        with mock.patch("ui.projects_page.ConfirmDialog.confirm", return_value=True):
            page._confirm_empty_trash()
        self.assertCountEqual(fired, [p1, p2])


class ProjectsPageModeTests(QtDbTestCase):
    def test_mode_switch_toggles_header(self) -> None:
        """模式切换：标题、头部按钮显隐随之翻转。"""
        page = self.track(ProjectsPage())
        page.set_mode("trash")
        self.assertEqual(page._title.text(), "回收站")
        self.assertTrue(page._new_btn.isHidden())
        self.assertFalse(page._restore_btn.isHidden())
        self.assertFalse(page._clear_btn.isHidden())
        page.set_mode("active")
        self.assertEqual(page._title.text(), "项目列表")
        self.assertFalse(page._new_btn.isHidden())
        self.assertTrue(page._restore_btn.isHidden())
        self.assertTrue(page._clear_btn.isHidden())

    def test_bulk_buttons_follow_emptiness(self) -> None:
        """全部恢复 / 清空回收站：空站禁用，有内容启用。"""
        page = self.track(ProjectsPage())
        page.set_mode("trash")
        self.assertFalse(page._restore_btn.isEnabled())
        self.assertFalse(page._clear_btn.isEnabled())
        repo = ProjectRepository()
        repo.soft_delete(repo.create("示例", {}).id)
        page.refresh()
        self.assertTrue(page._restore_btn.isEnabled())
        self.assertTrue(page._clear_btn.isEnabled())

    def test_empty_state_texts(self) -> None:
        """两种模式的空态文案。"""
        page = self.track(ProjectsPage())
        self.assertIn("暂无项目", page._grid.itemAt(0).widget().text())
        page.set_mode("trash")
        self.assertEqual(page._grid.itemAt(0).widget().text(), "回收站为空")

    def test_trash_card_click_does_not_open(self) -> None:
        """回收站卡片点击不打开项目；列表模式正常打开。"""
        repo = ProjectRepository()
        pid = repo.create("示例", {"industry": "电子"}).id
        repo.soft_delete(pid)
        page = self.track(ProjectsPage())
        fired: list[int] = []
        page.open_project.connect(fired.append)

        page.set_mode("trash")
        page._grid.itemAt(0).widget().click()
        self.assertEqual(fired, [])

        repo.restore(pid)
        page.set_mode("active")
        page._grid.itemAt(0).widget().click()
        self.assertEqual(fired, [pid])

    def test_context_menu_items_by_mode(self) -> None:
        """右键菜单：列表模式「删除」，回收站模式「恢复 / 彻底删除」。"""
        repo = ProjectRepository()
        proj = repo.create("示例", {})
        page = self.track(ProjectsPage())

        page._on_context_menu(page, QPoint(0, 0), proj)
        menu = page.findChild(PopupMenu)
        self.assertEqual([b.text() for b in menu.findChildren(QPushButton)], ["删除"])
        menu.close()
        # WA_DeleteOnClose 的对象需冲刷 DeferredDelete 后才真正销毁
        _app().sendPostedEvents(None, QEvent.DeferredDelete)

        repo.soft_delete(proj.id)
        page.set_mode("trash")
        page._on_context_menu(page, QPoint(0, 0), proj)
        menu = page.findChild(PopupMenu)
        self.assertEqual(
            [b.text() for b in menu.findChildren(QPushButton)], ["恢复", "彻底删除"]
        )
        menu.close()


class ProcessPageTests(unittest.TestCase):
    def test_heal_stale_status(self) -> None:
        """验证陈旧 running 状态的治愈判据：有检查点=中断，有数据=完成，否则草稿。"""
        from ui.process_page import ProcessPage  # 局部导入，避免 UI 依赖拖累其他用例

        heal = ProcessPage._heal_stale_status
        self.assertEqual(heal(has_checkpoint=True, has_data=True), "interrupted")
        self.assertEqual(heal(has_checkpoint=True, has_data=False), "interrupted")
        self.assertEqual(heal(has_checkpoint=False, has_data=True), "completed")
        self.assertEqual(heal(has_checkpoint=False, has_data=False), "draft")


class WorkspaceNavActionTests(QtDbTestCase):
    """Step3 导航主动作跟随仿真页状态：文案与可用性同源。"""

    def test_nav_mirrors_simulation_action_state(self) -> None:
        w = self.track(MainWindow())
        w._go(1)
        w._process._step = 2
        w._process._smp._set_action("⏸ 暂停")
        self.assertEqual(w._process._next.text(), "⏸ 暂停")
        w._process._smp._set_action("↺ 恢复仿真")
        self.assertEqual(w._process._next.text(), "↺ 恢复仿真")
        w._process._smp._set_action("✓ 已完成", False)
        self.assertFalse(w._process._next.isEnabled())


class SimulationHistorySpeechTests(QtDbTestCase):
    """发言回填回归：重开项目时日志须从 state_json 还原行为体发言。"""

    def test_history_speeches_backfilled(self) -> None:
        from core.agent_factory import AgentFactory
        from ui.simulation_page import SimulationPage, _format_speech_line

        page = self.track(SimulationPage())
        state = {
            "agent_states": {
                "2": {
                    "spoke": True,
                    "speech": "加快备货。",
                    "action_type": "replenish",
                    "reaction_to": "none",
                },
                "1": {
                    "spoke": True,
                    "speech": "收紧供应。",
                    "action_type": "adjust_supply",
                    "reaction_to": "制造商",
                },
                "3": {"spoke": False, "speech": ""},
            }
        }
        page._append_history_speeches(state)

        name1 = AgentFactory.get_template(1)["name"]
        name2 = AgentFactory.get_template(2)["name"]
        self.assertEqual(
            page._log.toPlainText().splitlines(),
            [
                _format_speech_line(name1, "adjust_supply", "制造商", "收紧供应。"),
                _format_speech_line(name2, "replenish", "none", "加快备货。"),
            ],
        )

    def test_history_speeches_tolerate_corrupt_state(self) -> None:
        """损坏的 state_json（缺 agent_states / 键非数值）不回填也不抛错。"""
        from ui.simulation_page import SimulationPage

        page = self.track(SimulationPage())
        page._append_history_speeches({})
        page._append_history_speeches({"agent_states": "坏数据"})
        page._append_history_speeches({"agent_states": {"x": {"spoke": True, "speech": "？"}}})
        self.assertEqual(page._log.toPlainText(), "")


if __name__ == "__main__":
    unittest.main()
