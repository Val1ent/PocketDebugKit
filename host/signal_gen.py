#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号发生器控制台：通过 USB CDC(COM4) 给设备发命令
  输入频率数字(如 1000) -> 设备输出该频率方波 (范围 1~5000Hz)
  输入 u                -> 切回软件 UART（发 Hello CH32）
  输入 q                -> 退出
用法： py -3.12 signal_gen.py
"""
import sys
import serial
from serial.tools import list_ports

def pick_port():
    ports = list(list_ports.comports())
    if not ports:
        print("没找到串口，检查 USB 连接")
        sys.exit(1)
    print("可用端口：")
    for i, p in enumerate(ports):
        print(f"  {i+1}. {p.device}  {p.description}")
    if len(ports) == 1:
        return ports[0].device
    s = input("选择端口序号(回车默认1): ").strip()
    idx = int(s) - 1 if s else 0
    return ports[idx].device

def main():
    port = pick_port()
    ser = serial.Serial(port, baudrate=921600, timeout=0.2)
    ser.reset_input_buffer()
    print(f"已连接 {port}")
    print("输入 频率数字(1~5000) 发方波；u 切 UART；q 退出\n")

    while True:
        try:
            cmd = input("signal> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        if cmd.lower() == 'q':
            break
        if cmd.lower() == 'u':
            ser.write(b"U\n")
            print("-> 切到 UART 模式")
        elif cmd.isdigit():
            ser.write(("S" + cmd + "\n").encode())
            print(f"-> 方波 {cmd} Hz")
        else:
            print("请输入数字频率，或 u / q")

    ser.close()
    print("已退出")

if __name__ == "__main__":
    main()
