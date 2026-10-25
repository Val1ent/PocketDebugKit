#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字调试助手 - 独立分析终端（不依赖 PulseView）
三合一：
  1) 自主 UART 解码：检测起始位，软件解出字符
  2) 终端波形显示：ASCII 实时画 D0 波形
  3) 数据记录 CSV：实时测量值 + 解码内容写入 CSV
采样率固定 10kHz，UART 1000bps（每 bit 10 点）。
用法： py -3.12 analyzer.py
"""
import os, sys, time, csv
from collections import deque

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("缺少 pyserial: py -3.12 -m pip install pyserial")
    input("回车退出..."); sys.exit(1)

SAMPLE_RATE   = 10000
DT            = 1.0 / SAMPLE_RATE
WINDOW        = 5000
TICKS_PER_BIT = 10
WAVE_LEN      = 100

def measure(bits):
    rising, falling = [], []
    for i in range(1, len(bits)):
        if bits[i-1] == 0 and bits[i] == 1: rising.append(i)
        if bits[i-1] == 1 and bits[i] == 0: falling.append(i)
    if len(rising) < 2:
        return None
    periods = [rising[i+1] - rising[i] for i in range(len(rising)-1)]
    period_s = (sum(periods) / len(periods)) * DT
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
    return {"freq": 1.0/period_s, "period": period_s, "high": high_s,
            "low": period_s - high_s, "duty": high_s/period_s*100.0}

def uart_decode(bits):
    """软件 UART 解码：返回解出的字符串"""
    out = []
    n = len(bits)
    i = 1
    while i < n:
        # 起始位：下降沿 1->0
        if bits[i-1] == 1 and bits[i] == 0:
            start = i
            mid = start + TICKS_PER_BIT // 2
            # 起始位中点应为 0
            if mid < n and bits[mid] == 0:
                byte = 0
                ok = True
                for bit in range(8):
                    pos = start + TICKS_PER_BIT//2 + TICKS_PER_BIT*(bit+1)
                    if pos >= n:
                        ok = False; break
                    if bits[pos] == 1:
                        byte |= (1 << bit)
                stop = start + TICKS_PER_BIT//2 + TICKS_PER_BIT*9
                if ok and stop < n and bits[stop] == 1:
                    out.append(chr(byte))
            i = start + TICKS_PER_BIT * 9
        else:
            i += 1
    return ''.join(out)

def scan_frames(bits):
    """扫描所有成功解码的 UART 帧，返回 [(起始位置, 字符)]"""
    frames = []
    n = len(bits)
    i = 1
    while i < n:
        if bits[i - 1] == 1 and bits[i] == 0:
            start = i
            mid = start + TICKS_PER_BIT // 2
            if mid < n and bits[mid] == 0:
                byte = 0
                ok = True
                for bit in range(8):
                    pos = start + TICKS_PER_BIT // 2 + TICKS_PER_BIT * (bit + 1)
                    if pos >= n:
                        ok = False; break
                    if bits[pos] == 1:
                        byte |= (1 << bit)
                stop = start + TICKS_PER_BIT // 2 + TICKS_PER_BIT * 9
                if ok and stop < n and bits[stop] == 1:
                    frames.append((start, chr(byte)))
                i = start + TICKS_PER_BIT * 9
            else:
                i += 1
        else:
            i += 1
    return frames

def best_packet(bits):
    """找出帧最多的连续报文，返回 (波形段, 字符串, 帧列表)"""
    frames = scan_frames(bits)
    if len(frames) < 2:
        return None
    groups = []
    cur = [frames[0]]
    for f in frames[1:]:
        if f[0] - cur[-1][0] <= TICKS_PER_BIT * 13:
            cur.append(f)
        else:
            groups.append(cur)
            cur = [f]
    groups.append(cur)
    g = max(groups, key=lambda x: len(x))
    if len(g) < 2:
        return None
    s0 = g[0][0]
    s1 = g[-1][0] + TICKS_PER_BIT * 10
    return bits[s0:s1], ''.join(c for _, c in g), g

def pick_port():
    ports = list(list_ports.comports())
    print("===== 检测到的串口 =====")
    for i, p in enumerate(ports):
        print(f"  [{i}]  {p.device}   {p.description}")
    sel = input("选择【底部 USB-FS 口】序号(回车重扫, q退出): ").strip()
    if sel.lower() == 'q': sys.exit(0)
    return ports[int(sel)].device

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    port = pick_port()
    ser = serial.Serial(port, 115200, timeout=0)
    ser.dtr = True; ser.rts = True
    time.sleep(0.5)
    ser.reset_input_buffer()

    csv_path = os.path.join(base, "analyzer_log.csv")
    csv_file = open(csv_path, "w", newline="", encoding="utf-8-sig")
    writer = csv.writer(csv_file)
    writer.writerow(["时间戳", "波特率bps", "字符周期ms", "报文长度", "解码内容"])

    raw = deque(maxlen=WINDOW)
    last_show = 0
    rows = 0
    print(f"\n已连接 {port}，独立分析中 ...（Ctrl+C 退出）\n")

    try:
        while True:
            n = ser.in_waiting
            if n:
                raw.extend(ser.read(n))
            else:
                time.sleep(0.01)

            if time.time() - last_show >= 0.5 and len(raw) >= 100:
                last_show = time.time()
                bits = [(b >> 0) & 1 for b in raw]
                pkt = best_packet(bits)
                if pkt:
                    seg, decoded, g = pkt
                    wave = ''.join('█' if x else '_' for x in seg[:WAVE_LEN])
                    gaps = [g[i + 1][0] - g[i][0] for i in range(len(g) - 1)]
                    char_period = (sum(gaps) / len(gaps)) * DT if gaps else 0.0
                    baud = SAMPLE_RATE / TICKS_PER_BIT
                    nchar = len(g)
                else:
                    seg = None; decoded = ""
                    wave = ''.join('█' if x else '_' for x in bits[-WAVE_LEN:])
                    char_period = 0.0; baud = 0.0; nchar = 0

                os.system('cls')
                print("===== 独立分析终端（不依赖 PulseView）=====")
                print(f"采样率: {SAMPLE_RATE} Hz   窗口: {len(raw)} 点\n")

                print("-- 终端波形 D0 (报文开头100点=10ms) --")
                print("  高=█  低=_")
                print("  " + wave + "\n")

                print("-- 串口参数测量 --")
                if nchar:
                    print(f"  波特率 {baud:.0f} bps | 字符周期 {char_period*1000:.3f} ms | "
                          f"报文长度 {nchar} 字符 | 帧格式 8N1")
                else:
                    print("  本窗口未识别到完整报文")

                print("\n-- 自主 UART 解码 --")
                print("  接收到: " + (repr(decoded) if decoded else "(本窗口未解码出完整帧)"))

                # 写 CSV
                if nchar:
                    writer.writerow([f"{time.time():.1f}", f"{baud:.0f}",
                        f"{char_period*1000:.3f}", f"{nchar}", decoded])
                    csv_file.flush()
                    rows += 1
                print(f"\n-- 数据记录 --  已写入 {rows} 行 -> {csv_path}")
    except KeyboardInterrupt:
        pass
    finally:
        csv_file.close()
        ser.close()
        print("\n已退出，CSV 已保存:", csv_path)

if __name__ == "__main__":
    main()
