"""通用 AI 调用工作线程。

Step1 文档分析、Step2 画像生成、Step4 结果分析、设置页连通性测试共用。
在 QThread 中执行传入的 callable，避免阻塞 UI 主线程。
"""
from PySide6.QtCore import QThread, Signal


class AIWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.succeeded.emit(self._fn())
        except Exception as e:  # noqa: BLE001 - 统一降级为错误文案
            self.failed.emit(str(e))


def run_ai_task(owner, fn, on_success, on_error):
    """启动一次 AI 任务并管理 worker 生命周期。

    owner 为页面实例（持有引用防止 GC）。worker 不设 parent：
    页面/窗口析构不会连带销毁运行中的 QThread（避免 abort），
    线程结束后经 finished → deleteLater 自行回收。
    """
    worker = AIWorker(fn)
    owner._ai_workers = getattr(owner, "_ai_workers", None) or []
    owner._ai_workers.append(worker)

    def _cleanup(*_args):
        if worker in owner._ai_workers:
            owner._ai_workers.remove(worker)

    worker.succeeded.connect(on_success)
    worker.failed.connect(on_error)
    worker.succeeded.connect(_cleanup)
    worker.failed.connect(_cleanup)
    worker.finished.connect(worker.deleteLater)
    worker.start()
    return worker
