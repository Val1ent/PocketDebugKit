# -*- coding: utf-8 -*-
"""测量面板：8 通道频率/占空比一览 + D0 详细指标。"""
from app_paths import ensure_host_path

ensure_host_path()

import measure  # noqa: E402  host/measure.py 的 measure(bits)

from PySide6.QtWidgets import (  # noqa: E402
    QFormLayout, QGroupBox, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

CHANNELS = 8
DETAIL_FIELDS = [
    ("频率", "freq", "Hz"),
    ("周期", "period", "ms"),
    ("高电平脉宽", "high", "ms"),
    ("低电平脉宽", "low", "ms"),
    ("占空比", "duty", "%"),
    ("周期 min", "pmin", "ms"),
    ("周期 max", "pmax", "ms"),
    ("统计周期数", "cycles", ""),
]


class MeasurePanel(QWidget):
    """8 行频率/占空比表格，另附 D0 详细指标。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(CHANNELS, 3)
        self.table.setHorizontalHeaderLabels(["通道", "频率(Hz)", "占空比(%)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        for ch in range(CHANNELS):
            self.table.setItem(ch, 0, QTableWidgetItem(f"D{ch}"))
            self.table.setItem(ch, 1, QTableWidgetItem("--"))
            self.table.setItem(ch, 2, QTableWidgetItem("--"))

        detail_box = QGroupBox("D0 详细")
        self.detail_form = QFormLayout(detail_box)
        self.detail_labels = {}
        for title, _key, unit in DETAIL_FIELDS:
            label = QLabel("--")
            self.detail_form.addRow(f"{title}:", label)
            self.detail_labels[_key] = (label, unit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(detail_box)

    def _update_row(self, ch, result):
        if result is None:
            self.table.item(ch, 1).setText("--")
            self.table.item(ch, 2).setText("--")
        else:
            self.table.item(ch, 1).setText(f"{result['freq']:.1f}")
            self.table.item(ch, 2).setText(f"{result['duty']:.1f}")

    def _update_detail(self, result):
        if result is None:
            for _key, (label, _unit) in self.detail_labels.items():
                label.setText("信号不足")
            return
        for _title, key, _unit in DETAIL_FIELDS:
            label, unit = self.detail_labels[key]
            if key == "cycles":
                label.setText(str(result[key]))
            elif unit == "ms":
                label.setText(f"{result[key] * 1000:.3f}")
            elif unit == "%":
                label.setText(f"{result[key]:.1f}")
            else:
                label.setText(f"{result[key]:.1f}")

    def set_data(self, rate, samples):
        """对 D0-D7 分别测量并刷新表格与 D0 详细区。"""
        n = len(samples)
        for ch in range(CHANNELS):
            bits = [1 if (s >> ch) & 1 else 0 for s in samples]
            if n < 2:
                result = None
            else:
                result = measure.measure(bits)
            self._update_row(ch, result)
            if ch == 0:
                self._update_detail(result)
