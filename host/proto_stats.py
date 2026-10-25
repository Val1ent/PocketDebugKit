#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 离线脉冲统计与毛刺检测
========================================================
对一个捕获文件（或解码器演示波形）做"事后体检"，每通道输出：
  1) 活动度：翻转次数、平均频率、平均占空比
  2) 脉冲宽度统计：最小/中位/平均/最大 + ASCII 直方图
  3) 毛刺检测：宽度 < 阈值的窄脉冲逐一列出（时间/宽度/电平）
  4) 静默检测：整段无跳变的通道（疑似悬空/常电平/未接线）
并把毛刺清单 + 汇总写入 CSV。纯只读离线分析，零烧录风险。

用法：
  py -3.12 proto_stats.py --demo servo
  py -3.12 proto_stats.py capture.sr [--glitch 200] [--ch 0,1]
  py -3.12 proto_stats.py data.bin --rate 10000
"""
import os, sys, csv, statistics
import proto_io
from proto_common import channel_bits, pulse_widths, DECKS

BINS_MS = [(0, 0.1), (0.1, 0.2), (0.2, 0.5), (0.5, 1), (1, 2), (2, 5),
           (5, 10), (10, 20), (20, 50), (50, 1e9)]
BIN_LABEL = ["<0.1ms", "0.1~0.2", "0.2~0.5", "0.5~1", "1~2", "2~5",
             "5~10", "10~20", "20~50", ">=50"]

def load(path, rate):
    if path.lower().endswith(".sr"):
        r, s = proto_io.read_sr(path)
        if rate:
            r = rate
        return r, s
    r = rate or 10000
    return r, proto_io.read_bin(path, r)[1]

def analyze(bits, rate, glitch_s):
    """单通道体检，返回指标 dict。"""
    n = len(bits)
    dt = 1.0 / rate
    segs = pulse_widths(bits, rate)     # [(start, level, width_s), ...]
    rises = [i for i in range(1, n) if bits[i - 1] == 0 and bits[i] == 1]
    falls = [i for i in range(1, n) if bits[i - 1] == 1 and bits[i] == 0]
    edges = len(rises) + len(falls)
    freq = None
    duty = None
    if len(rises) >= 2:
        per = statistics.mean([rises[k + 1] - rises[k]
                               for k in range(len(rises) - 1)]) * dt
        if per > 0:
            freq = 1.0 / per
            highs = []
            fi = 0
            for r in rises:
                while fi < len(falls) and falls[fi] <= r:
                    fi += 1
                if fi < len(falls):
                    highs.append(falls[fi] - r)
            if highs:
                duty = statistics.mean(highs) * dt / per * 100.0
    # 宽度统计：剔除首尾两个可能被截断的段
    body = segs[1:-1] if len(segs) >= 3 else segs
    widths = [w for (_, _, w) in body]
    stats = None
    if widths:
        stats = {"min": min(widths), "max": max(widths),
                 "mean": statistics.mean(widths),
                 "median": statistics.median(widths), "count": len(widths)}
    # 直方图
    hist = [0] * len(BINS_MS)
    for w in widths:
        for bi, (lo, hi) in enumerate(BINS_MS):
            if lo * 1e-3 <= w < hi * 1e-3:
                hist[bi] += 1
                break
    # 毛刺：比阈值窄的脉冲
    glitches = [(s, lvl, w) for (s, lvl, w) in body if w < glitch_s]
    return {"edges": edges, "freq": freq, "duty": duty, "stats": stats,
            "hist": hist, "glitches": glitches}

def report_channel(ch, res, rate, glitch_s):
    print(f"\n---- D{ch} ----")
    if res["edges"] == 0:
        print("  静默：整段无跳变（疑似悬空/常电平/未接线）")
        return
    line = f"  翻转 {res['edges']} 次"
    if res["freq"]:
        line += f" | 频率≈{res['freq']:.1f} Hz"
    if res["duty"] is not None:
        line += f" | 占空比≈{res['duty']:.1f}%"
    print(line)
    s = res["stats"]
    if s:
        print(f"  脉冲宽度: 最小 {s['min']*1e6:.0f}us | 中位 {s['median']*1e6:.0f}us | "
              f"平均 {s['mean']*1e6:.0f}us | 最大 {s['max']*1e6:.0f}us （{s['count']} 段）")
    mx = max(res["hist"]) or 1
    print("  宽度直方图:")
    for bi in range(len(BINS_MS)):
        c = res["hist"][bi]
        if c:
            print(f"    {BIN_LABEL[bi]:>8} {c:4d}  {'█' * max(1, int(c / mx * 36))}")
    if res["glitches"]:
        print(f"  [!] 毛刺（<{glitch_s*1e6:.0f}us）{len(res['glitches'])} 处:")
        for (s_i, lvl, w) in res["glitches"][:12]:
            print(f"    {s_i / rate * 1000:8.3f} ms  宽 {w*1e6:.0f}us  电平={lvl}")
        if len(res["glitches"]) > 12:
            print(f"    ... 其余 {len(res['glitches'])-12} 处见 CSV")
    else:
        print(f"  毛刺: 无（阈值 {glitch_s*1e6:.0f}us）")

def main():
    argv = sys.argv[1:]
    deck_name = None
    path = None
    rate = 10000
    glitch_us = 200.0
    chs = list(range(8))
    csv_path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--demo":
            deck_name = argv[i + 1]
            i += 2
        elif a == "--rate":
            rate = int(argv[i + 1])
            i += 2
        elif a == "--glitch":
            glitch_us = float(argv[i + 1])
            i += 2
        elif a == "--ch":
            chs = [int(x) for x in argv[i + 1].split(",")]
            i += 2
        elif a == "--csv":
            csv_path = argv[i + 1]
            i += 2
        elif not a.startswith("--"):
            path = a
            i += 1
        else:
            i += 1

    if deck_name:
        if deck_name not in DECKS:
            print("未知解码器:", deck_name, "可选:", list(DECKS))
            sys.exit(1)
        samples = DECKS[deck_name]["make"](rate)
        src = f"演示波形 {deck_name}（{DECKS[deck_name]['desc']}）"
    elif path:
        r, samples = load(path, rate)
        rate = r
        src = path
    else:
        print(__doc__)
        sys.exit(1)

    glitch_s = glitch_us * 1e-6
    print("=" * 64)
    print(f"脉冲统计与毛刺检测  |  {src}")
    print(f"采样率 {rate} Hz · {len(samples)} 点"
          f"（{len(samples)/rate*1000:.1f} ms） · 毛刺阈值 {glitch_us:.0f}us")
    results = {}
    for ch in chs:
        res = analyze(channel_bits(samples, ch), rate, glitch_s)
        results[ch] = res
        report_channel(ch, res, rate, glitch_s)

    out = csv_path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "proto_stats_报告.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["通道", "类别", "时间ms", "数值", "说明"])
        for ch in chs:
            r = results[ch]
            s = r["stats"]
            w.writerow([f"D{ch}", "SUMMARY", "", f"{r['edges']}", "翻转次数"])
            if r["freq"]:
                w.writerow([f"D{ch}", "SUMMARY", "", f"{r['freq']:.2f}", "平均频率Hz"])
            if r["duty"] is not None:
                w.writerow([f"D{ch}", "SUMMARY", "", f"{r['duty']:.2f}", "平均占空比%"])
            if s:
                w.writerow([f"D{ch}", "SUMMARY", "", f"{s['min']*1e6:.0f}", "最小脉宽us"])
                w.writerow([f"D{ch}", "SUMMARY", "", f"{s['max']*1e6:.0f}", "最大脉宽us"])
            for (s_i, lvl, wd) in r["glitches"]:
                w.writerow([f"D{ch}", "GLITCH", f"{s_i/rate*1000:.3f}",
                            f"{wd*1e6:.0f}us", f"电平={lvl}"])
    print(f"\n报告已导出: {out}")

if __name__ == "__main__":
    main()
