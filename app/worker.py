# -*- coding: utf-8 -*-
"""后台采集线程：把阻塞的串口采集/文件读取放到工作线程，避免界面卡死。"""
from PySide6.QtCore import QThread, Signal


def readable_error(exc):
    """把异常转成一行面向用户的文本（不暴露堆栈）。"""
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}（无详细信息）"


class AcquireWorker(QThread):
    """在后台线程执行一个可调用对象，通过信号回报结果。

    成功时发出 succeeded(int, list)（rate, samples）；
    失败时发出 failed(str)（可读错误信息）。
    """

    succeeded = Signal(int, list)
    failed = Signal(str)

    def __init__(self, fn, args=(), parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        try:
            rate, samples = self._fn(*self._args)
        except Exception as exc:
            self.failed.emit(readable_error(exc))
        else:
            self.succeeded.emit(rate, samples)
