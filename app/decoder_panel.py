# -*- coding: utf-8 -*-
"""解码面板：内置 UART 文本解码（D0, 8N1）+ 9 个注册解码器，结果以表格列出。"""
from app_paths import ensure_host_path

ensure_host_path()

import analyzer  # noqa: E402
import proto_extra  # noqa: E402,F401  注册 spi/stepper/encoder/rc5/ultrasonic/fan
from proto_common import DECKS  # noqa: E402

from PySide6.QtWidgets import (  # noqa: E402
    QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

UART_LABEL = "UART 文本 (D0, 8N1)"
HEADERS = ["时间(ms)", "通道", "类型", "内容"]


class DecoderPanel(QWidget):
    """选择解码器并运行，事件结果按时间顺序显示在表格中。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rate = 0
        self._samples = []

        self.decoder_combo = QComboBox()
        self.decoder_combo.addItem(UART_LABEL, None)
        for name, deck in DECKS.items():
            label = f"{name} - {deck['desc']}" if deck.get("desc") else name
            self.decoder_combo.addItem(label, name)

        self.run_button = QPushButton("运行解码")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_decode)

        top = QHBoxLayout()
        top.addWidget(QLabel("解码器:"))
        top.addWidget(self.decoder_combo, 1)
        top.addWidget(self.run_button)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)

    def set_data(self, rate, samples):
        """保存当前数据；清空旧解码结果（不自动重跑）。"""
        self._rate = rate
        self._samples = list(samples)
        self.clear_results()
        self.run_button.setEnabled(bool(self._samples) and rate > 0)

    def clear_results(self):
        self.table.setRowCount(0)
        self.status_label.setText("")

    def _run_uart(self):
        bits = [s & 1 for s in self._samples]          # D0
        events = []
        for start, char in analyzer.scan_frames(bits):
            events.append({
                "t": start / self._rate,
                "ch": 0,
                "type": "char",
                "text": char,
            })
        return events

    def run_decode(self):
        if not self._samples or self._rate <= 0:
            return
        name = self.decoder_combo.currentData()
        try:
            if name is None:
                events = self._run_uart()
            else:
                events = DECKS[name]["decode"](self._samples, self._rate)
        except Exception as exc:
            QMessageBox.warning(self, "解码失败", str(exc))
            return
        events.sort(key=lambda e: e["t"])
        self.table.setRowCount(0)
        self.table.setRowCount(len(events))
        for row, ev in enumerate(events):
            items = [
                QTableWidgetItem(f"{ev['t'] * 1000:.3f}"),
                QTableWidgetItem(f"D{ev['ch']}"),
                QTableWidgetItem(str(ev["type"])),
                QTableWidgetItem(str(ev["text"])),
            ]
            for col, item in enumerate(items):
                self.table.setItem(row, col, item)
        if events:
            self.status_label.setText(f"共解出 {len(events)} 条事件")
        else:
            self.status_label.setText("未解码出事件")
