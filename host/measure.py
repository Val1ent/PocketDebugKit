#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字调试助手 - 三合一实时测量（多通道 + 详细指标 + 边沿触发）
读取 CH32H417 8 通道数据，实时显示：
  1) 多通道频率（D0-D7）
  2) 主通道详细测量：频率/周期/高低电平脉宽/占空比/周期抖动(min,max)
  3) 边沿触发：各通道上升沿、下降沿累计计数
采样率固定 10kHz（每点 0.1ms）。
用法： py -3.12 measure.py
"""
import os, sys, time
from collections import deque

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("缺少 pyserial: py -3.12 -m pip install pyserial")
    input("回车退出..."); sys.exit(1)

SAMPLE_RATE = 10000
DT          = 1.0 / SAMPLE_RATE
WINDOW      = 3000
NCH         = 8

def measure(bits):
    """对单通道 0/1 序列测量，返回指标 dict，信号不足返回 None"""
    rising, falling = [], []
    for i in range(1, len(bits)):
        if bits[i-1] == 0 and bits[i] == 1: rising.append(i)
        if bits[i-1] == 1 and bits[i] == 0: falling.append(i)
    if len(rising) < 2:
        return None
    periods = [rising[i+1] - rising[i] for i in range(len(rising)-1)]
    per_avg = sum(periods) / len(periods)
    per_min = min(periods) * DT
    per_max = max(periods) * DT
    period_s = per_avg * DT
    freq = 1.0 / period_s

    highs = []
    fi = 0
    for r in rising:
        while fi < len(falling) and falling[fi] <= r:
            fi += 1
        if fi < len(falling):
            highs.append(falling[fi] - r)
    if not highs:
        return None
    high_s = (sum(highs) / len(highs)) * DT
    low_s  = period_s - high_s
    duty   = high_s / period_s * 100.0
    return {"freq": freq, "period": period_s, "high": high_s, "low": low_s,
            "duty": duty, "pmin": per_min, "pmax": per_max, "cycles": len(periods)}

def pick_port():
    ports = list(list_ports.comports())
    print("===== 检测到的串口 =====")
    for i, p in enumerate(ports):
        print(f"  [{i}]  {p.device}   {p.description}")
    sel = input("选择【底部 USB-FS 口】序号(回车重扫, q退出): ").strip()
    if sel.lower() == 'q': sys.exit(0)
    return ports[int(sel)].device

def main():
    port = pick_port()
    ser = serial.Serial(port, 115200, timeout=0)
    ser.dtr = True; ser.rts = True
    time.sleep(0.5)
    ser.reset_input_buffer()

    raw = deque(maxlen=WINDOW)          # 原始字节（8通道）
    rise_cnt = [0] * NCH                # 边沿触发累计
    fall_cnt = [0] * NCH
    prev = None
    last_show = 0
    print(f"\n已连接 {port}，实时测量中 ...（Ctrl+C 退出）\n")

    try:
        while True:
            n = ser.in_waiting
            if n:
                chunk = ser.read(n)
                for b in chunk:
                    # 边沿触发：与上一字节逐通道比较
                    if prev is not None:
                        for ch in range(NCH):
                            p = (prev >> ch) & 1
                            c = (b >> ch) & 1
                            if p == 0 and c == 1: rise_cnt[ch] += 1
                            if p == 1 and c == 0: fall_cnt[ch] += 1
                    prev = b
                    raw.append(b)
            else:
                time.sleep(0.01)

            if time.time() - last_show >= 0.5 and len(raw) >= 100:
                last_show = time.time()
                os.system('cls')
                print("===== 数字调试助手 · 三合一实时测量 =====")
                print(f"采样率: {SAMPLE_RATE} Hz   窗口: {len(raw)} 点\n")

                # 1) 多通道频率
                print("-- 多通道频率 --")
                results = []
                for ch in range(NCH):
                    bits = [(b >> ch) & 1 for b in raw]
                    results.append(measure(bits))
                    if results[ch]:
                        print(f"  D{ch}: {results[ch]['freq']:8.1f} Hz   占空比 {results[ch]['duty']:5.1f}%")
                    else:
                        print(f"  D{ch}:       --  (无周期信号)")

                # 2) 主通道 D0 详细测量
                m = results[0]
                print("\n-- D0 详细测量 --")
                if m:
                    print(f"  频率      : {m['freq']:.1f} Hz")
                    print(f"  周期      : {m['period']*1000:.3f} ms  "
                          f"(min {m['pmin']*1000:.3f} / max {m['pmax']*1000:.3f})")
                    print(f"  高电平脉宽: {m['high']*1000:.3f} ms")
                    print(f"  低电平脉宽: {m['low']*1000:.3f} ms")
                    print(f"  占空比    : {m['duty']:.1f} %   ({m['cycles']} 周期平均)")
                else:
                    print("  信号不足")

                # 3) 边沿触发计数
                print("\n-- 边沿触发累计 --")
                print("  通道   上升沿   下降沿")
                for ch in range(NCH):
                    print(f"   D{ch}   {rise_cnt[ch]:6d}   {fall_cnt[ch]:6d}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("\n已退出")

if __name__ == "__main__":
    main()
