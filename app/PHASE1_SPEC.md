# PocketDebugKit 图形界面软件 · Phase 1 施工规格书

> 本文件是**施工方（DeepSeek）**的唯一施工依据。技术负责人负责本规格与最终验收。
> 施工方只按本规格书写代码；不得擅自更改架构、接口、范围。规格书未覆盖处，做最小合理实现，并在交付说明中逐条列出。

---

## 1. 角色与分工

- 技术负责人：制定本规格、最终验收（逐条核对第 9 节）。
- 施工方（DeepSeek）：按本规格交付全部代码，保证可运行。
- 施工方不得改动任何现有文件（见第 8 节硬性约束）。

## 2. Phase 1 目标

把现有终端工具的核心能力，做成一个图形界面，用户用鼠标即可完成：

1. 选择串口（或打开采集文件）；
2. 采集一屏数据；
3. 以数字波形显示 8 个通道；
4. 选择解码器并运行，结果以表格列出（含能解出 `Hello CH32!` 的 UART 文本解码）；
5. 显示 8 通道测量结果（频率/占空比，以及 D0 详细指标）。

## 3. 明确不做（Phase 1 范围外）

- 不做实时连续采集（仅"采集一屏"的单次模式）；
- 不做信号发生控制面板；
- 不做打包 exe、设置保存、多语言、主题切换；
- 不修改任何现有 `host/*.py` 脚本与固件；
- 不新写任何协议解码算法（复用现有 9 个解码器 + 现有 UART 解码）。

## 4. 运行环境与依赖

- 操作系统：Windows；Python 3.12（启动器 `py -3.12`，实测 3.12.10）。
- 已安装：`pyserial 3.5`。
- 需安装：`py -3.12 -m pip install PySide6 pyqtgraph`（numpy 随 pyqtgraph 自动安装）。
- 运行命令：`py -3.12 app/main.py`。

## 5. 现有可复用接口（禁止改动，直接 import）

**路径处理**：`app/` 与 `host/` 同级。GUI 启动时必须先把 `host/` 的绝对路径加入 `sys.path`，再 import 下列模块。

### 5.1 数据格式（务必遵守）

- `samples`：`list[int]`，每个 int 是一个采样时刻的 8 通道快照（1 字节）。
  - bit0 = D0(PD0)，bit1 = D1(PD1)，…，bit7 = D7(PD7)；
  - 某通道电平 = `(sample >> ch) & 1`。
- `rate`：`int`，采样率 Hz（当前固件为 10000）。

### 5.2 解码器（`proto_common` / `proto_decoders` / `proto_extra`）

- 注册表：`proto_common.DECKS`，类型 `dict`，键为解码器名，值为
  `{"decode": 函数, "make": 函数, "desc": 说明字符串}`。
- 调用：`DECKS[name]["decode"](samples, rate) -> list[Event]`。
- `Event` 为 dict：`{"t": float(秒), "ch": int(通道), "type": str(类型), "text": str(可读文本)}`，按 `t` 升序。
- **重要**：`proto_common` 自身只 import 了 `proto_decoders`（注册 3 个：nec/servo/i2c）。
  为了让全部 9 个解码器注册，GUI 必须额外 `import proto_extra`（它会注册 spi/stepper/encoder/rc5/ultrasonic/fan）。
- 最终解码器共 9 个：`nec, servo, i2c, spi, stepper, encoder, rc5, ultrasonic, fan`。

### 5.3 UART 文本解码（`analyzer`，用于解出 `Hello CH32!`）

- `analyzer.scan_frames(bits) -> list[(start_index, char)]`，`bits` 为 D0 的 0/1 序列。
- 固件参数：1000 bps、8N1、LSB 先发、每 bit 10 个采样点。
- 把每个 `(start_index, char)` 转成一个 Event：
  `t = start_index / rate`、`ch = 0`、`type = "char"`、`text = char`。
- 该解码在 GUI 中作为一个内置项，名称显示为 `UART 文本 (D0, 8N1)`。

### 5.4 文件读取（`proto_io`）

- `read_sr(path) -> (rate, samples)`：读取 sigrok `.sr` 压缩包。
- `read_bin(path, rate) -> (rate, samples)`：读取原始 8 通道字节流，rate 由调用方给定（Phase 1 用 10000）。

### 5.5 测量（`measure`）

- `measure.measure(bits) -> dict 或 None`。
- `bits` 为单通道 0/1 序列；返回 dict 字段：
  `freq`(Hz)、`period`(s)、`high`(s)、`low`(s)、`duty`(%)、`pmin`(s)、`pmax`(s)、`cycles`(周期数)。
- 该模块内部按 10000 Hz 计算，与当前固件一致。

## 6. 目标文件结构

全部新增文件放在 `app/` 目录：

```
app/
├── main.py            # 程序入口
├── app_paths.py       # 把 host/ 加入 sys.path
├── datasource.py      # 数据源：串口枚举、串口采集、文件打开
├── worker.py          # 后台采集线程（QThread），避免界面卡死
├── waveform_view.py   # 8 通道数字波形组件（pyqtgraph）
├── decoder_panel.py   # 解码面板（含内置 UART 文本项 + 9 个 DECKS）
├── measure_panel.py   # 测量面板（8 通道频率/占空比 + D0 详细）
├── main_window.py     # 主窗口，组装全部组件
└── requirements.txt   # 依赖清单
```

### 6.1 `app_paths.py`

- 提供函数 `ensure_host_path()`：
  - 计算 `host/` 绝对路径（`app/` 的同级 `host/`）；
  - 若不在 `sys.path` 中，则插入到 `sys.path[0]`。
- 必须在 import 任何 `host` 模块之前调用。

### 6.2 `datasource.py`

提供以下函数（命名可等价，但签名与行为必须一致）：

- `SERIAL_RATE = 10000`
- `list_serial_ports() -> list[tuple[str, str]]`：返回 `[(设备名, 描述), ...]`，使用 `serial.tools.list_ports`。
- `acquire_serial(port: str, n_points: int, timeout: float = 8.0) -> tuple[int, list[int]]`：
  - `ser = serial.Serial(port, 115200, timeout=0)`；置 `ser.dtr = True`、`ser.rts = True`；
  - 短暂等待后 `reset_input_buffer()`；
  - 非阻塞轮询 `ser.in_waiting`，累计读到恰好 `n_points` 个字节，或达到 `timeout`；
  - 结束后必须 `ser.close()`；
  - 成功返回 `(10000, list(data))`；
  - 若超时且不足 `n_points`，抛出异常，信息说明实际收到字节数与排查建议（确认是数据口、A15->D0、其他程序未占用）。
- `acquire_file(path: str) -> tuple[int, list[int]]`：
  - `.sr` 扩展名（大小写不敏感）→ `proto_io.read_sr(path)`；
  - `.bin` 扩展名 → `proto_io.read_bin(path, SERIAL_RATE)`；
  - 其他扩展名或读取失败 → 抛出带可读信息的异常。

### 6.3 `worker.py`

- 定义 `class AcquireWorker(QThread)`：
  - 信号：`succeeded = Signal(int, list)`（rate, samples）、`failed = Signal(str)`；
  - 构造时接收一个可调用对象及其位置参数；
  - `run()` 中调用：成功则 `succeeded.emit(rate, samples)`，捕获异常则 `failed.emit(可读信息)`。
- 串口采集与文件读取都必须通过该线程执行，禁止在主线程直接做阻塞采集。

### 6.4 `waveform_view.py`

- 定义 `class WaveformView`（基于 pyqtgraph 的 `PlotWidget`）。
- 提供 `set_data(rate: int, samples: list[int])`：
  - 绘制 8 个通道的数字波形，**D0 在最上方**，D7 在最下方；
  - 波形为标准数字方波：水平段表示电平，相邻电平之间有垂直跳变边；
  - 每通道有固定垂直基线，高电平在基线之上固定高度；
  - 每个通道使用一种固定的区分颜色（8 种）；
  - 左侧显示通道标签 D0–D7；
  - 横轴为时间，按 `rate` 换算并以合适单位（如 ms）显示；
  - 支持鼠标滚轮缩放、按住拖动平移；
  - 数据更新后视图缩放到全部数据。
- 绘制须考虑性能（点数可能达数千到两万），使用 pyqtgraph 的高效曲线对象，避免逐点 addItem。

### 6.5 `decoder_panel.py`

- 定义 `class DecoderPanel(QWidget)`。
- 控件：
  - 解码器下拉框 `QComboBox`：第一项为 `UART 文本 (D0, 8N1)`，其后按名称列出 9 个 DECKS（显示名包含 `desc`）；
  - `运行解码` 按钮；
  - 结果表格 `QTableWidget`，列：`时间(ms)`、`通道`、`类型`、`内容`。
- 提供 `set_data(rate, samples)`：保存当前数据；数据为空时按钮置灰。
- 点击运行：
  - 若为内置 UART 项：取 D0 的 bits，调用 `analyzer.scan_frames`，按 5.3 转成 Event 列表；
  - 否则调用对应 `DECKS[name]["decode"](samples, rate)`；
  - 按时间顺序填充表格；无事件时表格为空并在状态栏（或面板提示）说明"未解码出事件"。
- 数据更新后自动清空旧结果（不自动重跑，等待用户点运行）。

### 6.6 `measure_panel.py`

- 定义 `class MeasurePanel(QWidget)`。
- 提供 `set_data(rate, samples)`：
  - 对 D0–D7 分别取 bits，调用 `measure.measure`，生成 8 行表格：`通道`、`频率(Hz)`、`占空比(%)`；无周期信号显示 `--`；
  - 另设 D0 详细区，显示：频率、周期（ms）、高电平脉宽（ms）、低电平脉宽（ms）、占空比（%）、周期 min/max（ms）、统计周期数；信号不足时显示"信号不足"。

### 6.7 `main_window.py`

- 定义 `class MainWindow(QMainWindow)`，窗口标题 `PocketDebugKit`。
- 顶部连接区（可用 QToolBar 或一个水平容器）：
  - 串口下拉框 `QComboBox`；`刷新串口` 按钮；
  - 采样点数 `QSpinBox`，默认 3000，范围 500–20000，步进 500；
  - `采集` 按钮：从当前选中串口采集一屏；
  - `打开文件` 按钮：用 `QFileDialog` 选择 `.sr` / `.bin`。
- 中部：左侧为 `WaveformView`（占主要宽度）；右侧为 `QTabWidget`，含两个标签页：`解码`（DecoderPanel）、`测量`（MeasurePanel）。
- 底部 `QStatusBar`：显示当前状态（如"正在采集…""已采集 N 点""就绪"）。
- 行为：
  - 启动时自动枚举串口并填充下拉框；
  - 点采集/打开文件时：禁用相关按钮，状态栏提示，启动 `AcquireWorker`；
  - 成功：把 `(rate, samples)` 同时交给波形、解码、测量三个组件，状态栏报告点数；
  - 失败：用 `QMessageBox.warning` 弹出可读错误，并在状态栏提示；
  - 结束（成功或失败）后恢复按钮可用。

### 6.8 `main.py`

- 先 `from app_paths import ensure_host_path; ensure_host_path()`；
- 创建 `QApplication`，显示 `MainWindow`，进入事件循环。
- 注意：`main.py` 作为入口时，`app/` 内模块之间的相互 import 必须在该运行方式下可用（处理好相对导入或同目录导入）。

### 6.9 `requirements.txt`

内容：

```
PySide6
pyqtgraph
pyserial
```

## 7. 交互与错误处理要求

- 所有采集与文件读取在后台线程进行，界面任何时候不得卡死。
- 错误信息必须可读、面向用户（说明发生了什么、可如何处理），不得直接抛出原始堆栈到界面。
- 数据到达后：波形自动全量显示，测量自动刷新，解码结果清空等待运行。
- 串口下拉框可随时通过刷新按钮重新枚举。
- 关闭窗口时确保后台线程结束、串口被关闭，无残留占用。

## 8. 硬性约束（违反即验收不通过）

1. 代码、注释、字符串、文档中**严禁**出现任何 AI 工具名（ChatGPT、DeepSeek、Copilot、Claude、Gemini、豆包等），**严禁**出现"AI 生成 / AI 辅助 / 由 AI 编写 / AI-powered / AI-generated"等任何字样与类似标记；**严禁**使用 emoji。
2. 不修改 `host/`、`firmware/`、`docs/`、仓库根目录下的任何现有文件；只在 `app/` 内新增文件。
3. 所有 `.py` 文件使用 UTF-8 编码，中文注释在编辑器与运行中正常显示。
4. 复用现有接口，不重复实现解码、测量、文件读取算法。
5. 代码清晰、函数短小、命名达意，不堆砌无用抽象，不保留无用注释或被注释掉的代码。

## 9. 验收标准（技术负责人逐条核对，全部通过才算合格）

1. 执行 `py -3.12 app/main.py` 能正常启动，无报错，窗口标题为 `PocketDebugKit`。
2. 启动后串口下拉框自动列出可用串口；`刷新串口` 可重新枚举。
3. 选择 CH32 数据口并点`采集`：界面不卡死，状态栏有进度提示；数秒内波形区显示 8 通道波形；A15 环回 D0 时 D0 可见 UART 波形。
4. 波形为标准数字方波（水平段 + 垂直跳变），D0 在最上、D7 在最下，D0–D7 标签正确，时间轴换算正确，可缩放与平移。
5. 解码下拉框首项为 `UART 文本 (D0, 8N1)`，其后为全部 9 个 DECKS（共 10 项）。
6. 对环回 UART 数据运行内置 UART 解码，能解出 `Hello CH32!` 字符，表格按时间列出每帧字符。
7. 对 9 个 DECKS 分别用其 `make(rate)` 生成的测试数据调用 `decode`，均能得到非空事件（此条由验收方做回归核对，施工方须保证调用方式正确）。
8. 测量面板：对 1 kHz 方波数据，D0 频率约 1000 Hz、占空比约 50%；D0 详细指标（频率/周期/高低电平/占空比/min/max/周期数）齐全。
9. `打开文件` 能打开 `host/examples/` 下的 `.sr`，正确显示波形并刷新测量。
10. 错误处理：选择无法打开的串口或无效文件时，弹出可读错误，程序不崩溃、不卡死，之后可正常再次操作。
11. 关闭程序正常，无后台线程残留、无串口占用。
12. 全量代码检查符合第 8 节：无 AI 标记、无 emoji、未改动现有文件、UTF-8 编码。

## 10. 交付物清单（施工方交付时附说明）

- `app/` 下第 6 节列出的全部文件；
- 一份简短交付说明：如何安装依赖、如何运行、每个文件的职责、已知限制（若有）。
