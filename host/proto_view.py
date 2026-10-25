#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 统一协议分析终端
====================================
基于注册表 DECKS，自动支持所有已登记的协议解码器（UART扩展、NEC、舵机、I2C...）。

两种模式：
  1) 实时串口：从底部 USB-FS 口采集，实时解码（与真实/自测信号配合）
  2) 离线演示：用各解码器自带的测试波形演示，无需任何硬件

用法： py -3.12 proto_view.py
"""
import os, sys, time
from collections import deque

import proto_common
from proto_common import DECKS, print_events

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

SAMPLE_RATE = 10000
WINDOW = 3000

def pick_decoder():
    names = list(DECKS.keys())
    print("===== 可选协议解码器 =====")
    for i, n in enumerate(names):
        print(f"  [{i}]  {n:<8} {DECKS[n]['desc']}")
    sel = input("选择解码器序号: ").strip()
    return names[int(sel)]

def offline_demo(name):
    print(f"\n===== 离线演示：{name}（自带测试波形，无需硬件）=====")
    samples = DECKS[name]["make"](SAMPLE_RATE)
    events = DECKS[name]["decode"](samples, SAMPLE_RATE)
    print_events(events)
    print(f"\n（共 {len(samples)} 个采样点，{len(events)} 个事件）")

def pick_port():
    ports = list(list_ports.comports())
    print("===== 检测到的串口 =====")
    for i, p in enumerate(ports):
        print(f"  [{i}]  {p.device}   {p.description}")
    sel = input("选择【底部 USB-FS 口】序号: ").strip()
    return ports[int(sel)].device

def live_mode(name):
    if serial is None:
        print("缺少 pyserial: py -3.12 -m pip install pyserial")
        return
    port = pick_port()
    ser = serial.Serial(port, 115200, timeout=0)
    ser.dtr = True; ser.rts = True
    time.sleep(0.5)
    ser.reset_input_buffer()

    raw = deque(maxlen=WINDOW)
    shown = set()           # 已打印事件去重
    last = 0
    print(f"\n已连接 {port}，实时解码【{name}】中 ...（Ctrl+C 退出）\n")
    try:
        while True:
            n = ser.in_waiting
            if n:
                raw.extend(ser.read(n))
            else:
                time.sleep(0.01)
            if time.time() - last >= 0.5 and len(raw) >= 50:
                last = time.time()
                samples = list(raw)
                events = DECKS[name]["decode"](samples, SAMPLE_RATE)
                for e in events:
                    key = (e["type"], e["text"], int(e["t"] * 10))
                    if key not in shown:
                        shown.add(key)
                        print(f"  {e['t']*1000:9.3f} ms  D{e['ch']}  "
                              f"{e['type']:<10} {e['text']}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("\n已退出。")

def main():
    if not DECKS:
        print("没有已登记的解码器，请确认 proto_decoders.py 在同一目录。")
        return
    print("===== 口袋数字调试助手 · 统一协议分析 =====")
    print("  [1] 实时串口解码（需硬件）")
    print("  [2] 离线演示（自带测试波形，无需硬件）")
    mode = input("选择模式: ").strip()
    name = pick_decoder()
    if mode == "1":
        live_mode(name)
    else:
        offline_demo(name)

if __name__ == "__main__":
    main()
