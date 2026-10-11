"""本步保存的公共流程：变更判定、二次放弃与失效确认。

放弃指纹等交互状态由本对象持有，保证两次「下一步」之间的判定连续；
失效确认弹窗以页面为父窗口展示，落库与表单恢复留在各页面。
"""
from __future__ import annotations

import json
from typing import Callable

from ui.widgets import ConfirmDialog

# 保存时项目已被删除的提示文案
MISSING_PROJECT_MESSAGE = "项目已被删除，请回到首页重新创建或打开其他项目"


class SaveFlow:
    """页面内本步保存的流程骨架。

    resolve 返回的去向：
    - "skip"：无改动，不落库直接继续
    - "commit"：有改动，落库后继续
    - "commit_invalidate"：失效确认通过，清除旧仿真结果后落库
    - "discard"：复点放弃，恢复表单后继续
    - "defer"：本次取消保存，停留原地
    """

    def __init__(self, page):
        self._page = page
        self._discard_snapshot: str | None = None

    def reset(self) -> None:
        """清空放弃指纹（切换或重置项目时调用）。"""
        self._discard_snapshot = None

    def resolve(
        self,
        *,
        changed: bool,
        status: str | None,
        payload: dict,
        confirm_text: str,
    ) -> str:
        """判定本次保存的去向，返回值语义见类说明。

        changed 由调用方以「当前表单与载入时表单的比对」得出，不受库中存储格式影响。
        """
        if not changed:
            self._discard_snapshot = None
            return "skip"
        if status not in ("completed", "interrupted"):
            self._discard_snapshot = None
            return "commit"
        fingerprint = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if fingerprint == self._discard_snapshot:
            self._discard_snapshot = None
            return "discard"
        if not ConfirmDialog.confirm(
            self._page,
            "保存并清除仿真结果",
            confirm_text,
            ok_text="保存并清除",
            danger=True,
        ):
            self._discard_snapshot = fingerprint
            return "defer"
        self._discard_snapshot = None
        return "commit_invalidate"

    def settle(
        self,
        log: Callable[..., None],
        outcome: str,
        restore: Callable[[], None],
        emit_saved: Callable[[], None],
    ) -> bool:
        """处理判定后的 discard / defer 分支；返回 True 表示本次保存到此为止。"""
        if outcome == "discard":
            restore()
            log("已放弃未保存的修改")
            emit_saved()
            return True
        if outcome == "defer":
            log("本步修改未保存；再点「下一步」将放弃修改并继续")
            return True
        return False
