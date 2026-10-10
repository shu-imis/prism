"""保存流程测试：变更判定、二次放弃与失效确认。"""
from __future__ import annotations

import unittest
from unittest import mock

from ui.save_flow import SaveFlow


class SaveFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._flow = SaveFlow(None)

    def _resolve(self, *, changed=True, status="draft", payload=None, confirmed=True):
        with mock.patch("ui.save_flow.ConfirmDialog.confirm", return_value=confirmed):
            return self._flow.resolve(
                changed=changed,
                status=status,
                payload={"a": 1} if payload is None else payload,
                confirm_text="变更说明",
            )

    def test_unchanged_skips_without_dialog(self) -> None:
        """无改动直达，不弹确认框。"""
        with mock.patch("ui.save_flow.ConfirmDialog.confirm") as confirm:
            outcome = self._flow.resolve(
                changed=False,
                status="completed",
                payload={"a": 1},
                confirm_text="变更说明",
            )
        self.assertEqual(outcome, "skip")
        confirm.assert_not_called()

    def test_non_result_status_commits_without_dialog(self) -> None:
        """项目未出过仿真结果：有改动直接落库，不弹确认框。"""
        with mock.patch("ui.save_flow.ConfirmDialog.confirm") as confirm:
            outcome = self._flow.resolve(
                changed=True,
                status="draft",
                payload={"a": 1},
                confirm_text="变更说明",
            )
        self.assertEqual(outcome, "commit")
        confirm.assert_not_called()

    def test_confirmed_invalidation_commits(self) -> None:
        """completed/interrupted 项目确认后清旧结果再落库。"""
        self.assertEqual(self._resolve(status="completed", confirmed=True), "commit_invalidate")
        self.assertEqual(self._resolve(status="interrupted", confirmed=True), "commit_invalidate")

    def test_declined_then_repeat_discards(self) -> None:
        """拒绝后未再编辑：同内容复点转为放弃，指纹不受键顺序影响。"""
        self.assertEqual(
            self._resolve(status="completed", payload={"a": 1, "b": 2}, confirmed=False),
            "defer",
        )
        self.assertEqual(
            self._resolve(status="completed", payload={"b": 2, "a": 1}), "discard"
        )

    def test_edited_after_decline_asks_again(self) -> None:
        """拒绝后继续编辑：复点重新走确认而非直接放弃。"""
        self.assertEqual(self._resolve(status="completed", confirmed=False), "defer")
        self.assertEqual(
            self._resolve(status="completed", payload={"a": 2}, confirmed=True),
            "commit_invalidate",
        )


if __name__ == "__main__":
    unittest.main()
