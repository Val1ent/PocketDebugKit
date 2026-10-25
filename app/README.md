# PocketDebugKit Phase 1 交付说明

## 安装依赖

Windows + Python 3.12（启动器 `py -3.12`）：

```
py -3.12 -m pip install -r app/requirements.txt
```

依赖清单：PySide6、pyqtgraph（自动带 numpy）、pyserial（本机已装 3.5 可跳过）。

## 运行

```
py -3.12 app/main.py
```

运行前把 CH32 数据口（底部 USB-FS 口，非调试口）接到电脑；若要看 UART 波形，
按固件说明把 A15 环回到 D0。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| main.py | 程序入口：先加 host/ 到 sys.path，再创建窗口进入事件循环 |
| app_paths.py | 计算 host/ 绝对路径并插入 sys.path[0] |
| datasource.py | 串口枚举、串口单次采集（115200，读满点数或超时）、.sr/.bin 文件读取 |
| worker.py | AcquireWorker 后台线程：阻塞采集不卡界面，成功/失败经信号回报 |
| waveform_view.py | 8 通道数字方波图（D0 在上），游程压缩 + pairs 连线，滚轮缩放/拖动平移 |
| decoder_panel.py | 解码下拉框（首项内置 UART 文本，后接 9 个 DECKS）与结果表格 |
| measure_panel.py | 8 通道频率/占空比表格 + D0 详细指标（信号不足时显示提示） |
| main_window.py | 主窗口：工具栏、波形 + 解码/测量页签、状态栏、后台任务与错误弹窗 |

## 已知限制

- Phase 1 只有单次采集（采集一屏），无实时连续刷新。
- UART 文本解码按固件参数固定为 D0、1000 bps、8N1、每 bit 10 采样点。
- 测量复用 host/measure，内部按 10 kHz 计算；打开的非 10 kHz 文件，
  波形时间轴按文件实际采样率显示，但频率/脉宽数值按 10 kHz 解释。
- 9 个协议解码器针对 10 kHz 采样下的慢速信号；快速总线超出采样能力。
- 采集超时（默认 8 秒）会弹窗提示实际收到的点数与排查建议。
- 关窗时若有采集进行中，会等待该次采集结束（最长约采集超时时间）再退出，
  保证串口关闭、无后台线程残留。
