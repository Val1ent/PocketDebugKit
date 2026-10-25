# Pocket Digital Debug Kit — CH32H417 Logic Analyzer (Extended)

A pocket-sized **analyze + generate + measure** all-in-one digital debug tool
based on the WCH **CH32H417** (RISC-V, QingKe V3F, 100 MHz).

> 口袋数字调试助手：基于沁恒 CH32H417（RISC-V）的"分析 + 发生 + 测量"三合一数字调试工具。

## Features / 功能

- **Logic Analyzer** — 8 channels (PD0–PD7), 10 kHz sampling, streamed over USB2.0 Full-Speed CDC.
- **Self-contained decoding** — decodes UART to text directly in Python (no PulseView needed), logs to CSV.
- **Signal Generator** — outputs a stable 1 kHz square wave (or a software-UART test message) for a self-loop test: the device generates, captures and decodes its own signal.
- **Real-time Measurement** — frequency, period, high/low pulse width, duty cycle, jitter (min/max), multi-channel.
- **Edge Trigger & Counting** — rising/falling edge detection and counting per channel.
- **Extensible Protocol Framework** — 9 protocol decoders with a unified analysis terminal.

## Data Path / 数据链路

```
GPIO sampling → USB2.0 CDC bulk upload → PC Python receive → display / decode / log
```

## Hardware / 硬件

| Item | Spec |
|---|---|
| Board | MuseLab nanoCH32H417 (CH32H417QEU6) |
| Core | WCH QingKe V3F RISC-V, single core, 100 MHz |
| Specs | 8 channels / 10 kHz / USB2.0 Full-Speed CDC |
| Link | A15 (PA15, generator) wired back to D0 (PD0, sampler) |

## Quick Start / 快速开始

1. Flash `firmware/UART_10kHz.hex` (or `.bin`) with MounRiver Studio / OpenOCD via WCH-Link.
2. Connect **A15 → D0** with a jumper wire.
3. Run the host tools with Python 3.12 (`pip install pyserial pillow`):

```bash
python host/capture3.py    # capture and build a PulseView .sr
python host/analyzer.py    # standalone analysis terminal (UART + waveform + CSV)
python host/measure.py     # real-time measurement
python host/proto_lab.py --selftest   # run all 9 protocol self-tests
```

## Protocol Decoders / 协议解码器

| Protocol | Decodes | Typical use |
|---|---|---|
| UART | start/data/stop bits → characters | serial debug |
| NEC IR | address, command, repeat code | remote control |
| RC-5 IR | address, command, toggle bit | European remote |
| Servo PWM/PPM | pulse width, angle, multi-channel | RC / robotics |
| I2C (slow) | start/stop, address, data, ACK | sensors / OLED |
| SPI (slow) | CS, MOSI/MISO, CPOL/CPHA | memory / display |
| Stepper | steps, direction, speed, position | CNC / 3D printing |
| Quadrature Encoder | 4x count, direction, RPM, index | motor loop / knob |
| HC-SR04 Ultrasonic | echo time, distance | ranging / obstacle |
| Fan TACH | pulse interval, RPM | fan monitoring |

> Note: limited by the 10 kHz sampling rate, I2C/SPI are designed for "slow" speed.
> Standard rates will be supported once the sampling rate is increased.

## Repository Layout / 目录结构

```
firmware/      prebuilt firmware (.hex/.bin)
host/          Python host tools
host/examples/ sample .sr captures and a CSV log example
docs/          BOM and documentation
```

## Roadmap / 后续规划

16 channels, 200 MHz sampling, USB3.0 high-speed upload, burst sampling
architecture, in-firmware edge triggering.

## License

Released under the **GNU General Public License v3.0 (GPL-3.0)**. See [LICENSE](LICENSE).
