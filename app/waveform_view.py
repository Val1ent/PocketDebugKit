# -*- coding: utf-8 -*-
"""8 通道数字波形组件（基于 pyqtgraph）。

每个通道画一条标准数字方波：水平段表示电平，电平变化处为垂直跳变边。
D0 在最上方，D7 在最下方，通道标签显示在左侧。
绘制时先把每通道波形按电平游程压缩（RLE），再用 connect='pairs' 的
PlotCurveItem 成对连线，避免逐点 addItem，保证数千到两万点也能流畅缩放。
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

CHANNELS = 8
CH_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45",
]
BASE = 1.0        # 相邻通道基线间距
HEIGHT = 0.7      # 高电平相对基线的高度


class WaveformView(QWidget):
    """8 通道数字波形图。调用 set_data(rate, samples) 更新显示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot)

        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "时间", units="s")
        self.plot.setLabel("left", "通道")
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        self._curves = []
        for ch in range(CHANNELS):
            curve = self.plot.plot(
                [], [],
                pen=pg.mkPen(CH_COLORS[ch], width=1.2),
                connect="pairs",
            )
            curve.setClipToView(True)
            self._curves.append(curve)

        # 左侧 y 轴刻度：从上到下 D0..D7，标在各自电平区间中点
        ticks = [
            (BASE * (CHANNELS - 1 - ch) + HEIGHT / 2.0, f"D{ch}")
            for ch in range(CHANNELS)
        ]
        self.plot.getAxis("left").setTicks([ticks])
        self.plot.setYRange(-0.2, BASE * (CHANNELS - 1) + HEIGHT + 0.2)

    @staticmethod
    def _square_points(x, levels):
        """把 0/1 电平序列转为带垂直跳变边的方波折线顶点。

        返回 (px, py)：相邻两点连线；折线依次为水平段、垂直段交替，
        供 connect='pairs' 按点对绘制。
        """
        n = len(levels)
        if n == 0:
            return np.zeros(0), np.zeros(0)
        dt = x[1] - x[0] if n > 1 else 0.0
        changed = np.empty(n, dtype=bool)
        changed[0] = True
        changed[1:] = levels[1:] != levels[:-1]
        idx = np.nonzero(changed)[0]          # 每个电平游程的起点
        run_end = np.empty(len(idx), dtype=np.float64)
        if len(idx) > 1:
            run_end[:-1] = x[idx[1:] - 1] + dt
        run_end[-1] = x[-1] + dt
        run_lvl = levels[idx]

        # 顶点序列：每个游程贡献 (起点, 电平) 与 (终点, 电平) 两点；
        # 相邻游程首尾相接，两点之间即为垂直跳变边。
        vx = np.empty(2 * len(idx), dtype=np.float64)
        vy = np.empty(2 * len(idx), dtype=np.float64)
        vx[0::2] = x[idx]
        vx[1::2] = run_end
        vy[0::2] = run_lvl
        vy[1::2] = run_lvl
        # 中间顶点重复一次，使相邻点对恰好连成各条线段
        px = np.repeat(vx, 2)[1:-1]
        py = np.repeat(vy, 2)[1:-1]
        return px, py

    def set_data(self, rate, samples):
        """用 (rate, samples) 重绘 8 通道波形并缩放到全部数据。"""
        n = len(samples)
        if n == 0 or rate <= 0:
            for curve in self._curves:
                curve.setData([], [])
            self.plot.setXRange(0, 1)
            return
        x = np.arange(n, dtype=np.float64) / rate
        arr = np.asarray(samples, dtype=np.uint8)
        for ch in range(CHANNELS):
            levels = ((arr >> ch) & 1).astype(np.float64)
            px, py = self._square_points(x, levels)
            y_base = BASE * (CHANNELS - 1 - ch)
            self._curves[ch].setData(px, py * HEIGHT + y_base)
        self.plot.setXRange(0, n / rate, padding=0)
