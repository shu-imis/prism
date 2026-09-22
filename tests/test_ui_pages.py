from __future__ import annotations

import unittest


class ProcessPageTests(unittest.TestCase):
    def test_heal_stale_status(self) -> None:
        """验证陈旧 running 状态的治愈判据：有检查点=中断，有数据=完成，否则草稿。"""
        from ui.process_page import ProcessPage  # 局部导入，避免 UI 依赖拖累其他用例

        heal = ProcessPage._heal_stale_status
        self.assertEqual(heal(has_checkpoint=True, has_data=True), "interrupted")
        self.assertEqual(heal(has_checkpoint=True, has_data=False), "interrupted")
        self.assertEqual(heal(has_checkpoint=False, has_data=True), "completed")
        self.assertEqual(heal(has_checkpoint=False, has_data=False), "draft")


if __name__ == "__main__":
    unittest.main()
