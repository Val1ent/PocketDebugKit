# -*- coding: utf-8 -*-
"""PocketDebugKit Phase 1 图形界面入口。

用法： py -3.12 app/main.py
"""
import sys

from app_paths import ensure_host_path

ensure_host_path()

from PySide6.QtWidgets import QApplication  # noqa: E402

from main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PocketDebugKit")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
