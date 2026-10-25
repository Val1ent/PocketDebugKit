# -*- coding: utf-8 -*-
"""主窗口：连接区（串口/点数/采集/打开文件）+ 波形 + 解码/测量页签 + 状态栏。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget, QToolBar,
)

import datasource
from decoder_panel import DecoderPanel
from measure_panel import MeasurePanel
from waveform_view import WaveformView
from worker import AcquireWorker

POINTS_DEFAULT = 3000
POINTS_MIN = 500
POINTS_MAX = 20000
POINTS_STEP = 500


class MainWindow(QMainWindow):
    """PocketDebugKit 主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PocketDebugKit")
        self._worker = None
        self._closing = False

        self._build_toolbar()
        self._build_central()
        self.statusBar().showMessage("就绪")
        self.refresh_ports()
        self.resize(1280, 760)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_toolbar(self):
        toolbar = QToolBar("采集控制")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel(" 串口:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(260)
        toolbar.addWidget(self.port_combo)

        self.refresh_button = QPushButton("刷新串口")
        self.refresh_button.clicked.connect(self.refresh_ports)
        toolbar.addWidget(self.refresh_button)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" 采样点数:"))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(POINTS_MIN, POINTS_MAX)
        self.points_spin.setSingleStep(POINTS_STEP)
        self.points_spin.setValue(POINTS_DEFAULT)
        toolbar.addWidget(self.points_spin)

        self.acquire_button = QPushButton("采集")
        self.acquire_button.clicked.connect(self.acquire_serial)
        toolbar.addWidget(self.acquire_button)

        self.open_button = QPushButton("打开文件")
        self.open_button.clicked.connect(self.open_file)
        toolbar.addWidget(self.open_button)

    def _build_central(self):
        self.waveform = WaveformView()
        self.decoder = DecoderPanel()
        self.measure = MeasurePanel()

        tabs = QTabWidget()
        tabs.addTab(self.decoder, "解码")
        tabs.addTab(self.measure, "测量")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.waveform)
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([880, 380])
        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    # 串口
    # ------------------------------------------------------------------
    def refresh_ports(self):
        self.port_combo.clear()
        for device, description in datasource.list_serial_ports():
            self.port_combo.addItem(f"{device} - {description}", device)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("（未检测到串口）", None)
            self.port_combo.setEnabled(False)
        else:
            self.port_combo.setEnabled(True)

    # ------------------------------------------------------------------
    # 采集与文件
    # ------------------------------------------------------------------
    def acquire_serial(self):
        port = self.port_combo.currentData()
        if port is None:
            QMessageBox.warning(
                self, "无法采集",
                "未检测到可用串口。请确认 CH32 数据口已连接，然后点击刷新串口。",
            )
            return
        points = self.points_spin.value()
        self._start_job(
            datasource.acquire_serial, (port, points),
            f"正在从 {port} 采集 {points} 点…",
        )

    def open_file(self):
        start_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "host", "examples",
        )
        path, _filter = QFileDialog.getOpenFileName(
            self, "打开采集文件", start_dir, "采集文件 (*.sr *.bin);;所有文件 (*)",
        )
        if not path:
            return
        self._start_job(datasource.acquire_file, (path,), "正在读取文件…")

    def _start_job(self, fn, args, status):
        self._set_busy(True)
        self.statusBar().showMessage(status)
        self._worker = AcquireWorker(fn, args, parent=self)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _set_busy(self, busy):
        for widget in (self.acquire_button, self.open_button,
                       self.refresh_button):
            widget.setEnabled(not busy)

    def _on_success(self, rate, samples):
        if self._closing:
            return
        self.waveform.set_data(rate, samples)
        self.decoder.set_data(rate, samples)
        self.measure.set_data(rate, samples)
        self.statusBar().showMessage(
            f"已采集 {len(samples)} 点（{rate} Hz）")

    def _on_failure(self, message):
        if self._closing:
            return
        QMessageBox.warning(self, "采集失败", message)
        self.statusBar().showMessage("采集失败")

    def _on_finished(self):
        self._set_busy(False)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    # ------------------------------------------------------------------
    # 退出
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        # 等后台线程收尾（串口采集最长不超过采集超时），避免残留占用
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._closing = True
            self.statusBar().showMessage("正在等待后台采集结束…")
            waited = 0.0
            while worker.isRunning() and waited < 20.0:
                worker.wait(100)
                waited += 0.1
                QApplication.processEvents()
        super().closeEvent(event)
