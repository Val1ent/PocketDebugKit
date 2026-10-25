#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 双波形对比 / 回归分析
========================================================
把两次捕获逐采样点对比：A=基准(黄金)波形，B=待测波形。适合：
  · 固件/电路改动后抓同一路信号做回归核对（行为一致性）
  · 排查偶发差异：差异时间点、差异通道、差异片段
输出：总体相似度、每通道差异点数与占比、首个差异时刻、差异区间数、
      围绕首个差异的 ASCII 对照带；并把差异区间清单导出 CSV。
纯只读离线分析：零烧录、不碰固件、不影响被测板。

用法：
  py -3.12 proto_diff.py A.sr B.sr
  py -3.12 proto_diff.py A.bin B.bin --rate 10000 [--csv 报告.csv]
"""
import os, sys, csv
import proto_io
from proto_common import channel_bits

def load(path, rate):
    """读取 .sr 或 .bin → (rate, samples)。"""
    if path.lower().endswith(".sr"):
        r, s = proto_io.read_sr(path)
        if rate:
            r = rate
        return r, s
    r = rate or 10000
    return r, proto_io.read_bin(path, r)[1]

def diff_segments(a_bits, b_bits):
    """返回差异区间 [(start, end_exclusive), ...]。"""
    segs = []
    start = None
    for i in range(len(a_bits)):
        if a_bits[i] != b_bits[i]:
            if start is None:
                start = i
        else:
            if start is not None:
                segs.append((start, i))
                start = None
    if start is not None:
        segs.append((start, len(a_bits)))
    return segs

def run(path_a, path_b, rate=None, csv_path=None):
    r, A = load(path_a, rate)
    _, B = load(path_b, rate)
    n = min(len(A), len(B))
    dt = 1.0 / r
    print("=" * 64)
    print("双波形对比报告（A=基准 · B=待测）")
    print(f"A = {path_a}  ({len(A)} 点)")
    print(f"B = {path_b}  ({len(B)} 点)")
    if len(A) != len(B):
        print(f"长度不同：仅对比重叠部分 {n} 点")
    print("=" * 64)

    first_global = None
    per = []
    for ch in range(8):
        ab = channel_bits(A, ch)[:n]
        bb = channel_bits(B, ch)[:n]
        segs = diff_segments(ab, bb)
        cnt = sum(e - s for (s, e) in segs)
        if cnt and (first_global is None or segs[0][0] < first_global):
            first_global = segs[0][0]
        per.append((ch, cnt, segs))

    total = sum(c for (_, c, _) in per)
    sim = 100.0 * (1.0 - total / (n * 8.0)) if n else 100.0
    print(f"\n总体相似度: {sim:.4f}%   差异采样点: {total} / {n * 8}")
    if first_global is not None:
        print(f"首个差异: {first_global * dt * 1000:.3f} ms (第 {first_global} 点)")
    print("\n通道     差异点     占比     差异区间数")
    for (ch, cnt, segs) in per:
        print(f"  D{ch}    {cnt:7d}   {cnt / n * 100:6.2f}%    {len(segs):6d}")

    # ASCII 对照带：围绕首个差异
    if first_global is not None:
        w = 80
        lo = max(0, first_global - w // 2)
        hi = min(n, lo + w)
        print(f"\n-- 局部对照（第 {lo}~{hi} 点，█=高 _=低 ^=差异）--")
        for ch in range(8):
            ab = channel_bits(A, ch)[:n]
            bb = channel_bits(B, ch)[:n]
            la = "".join("█" if ab[i] else "_" for i in range(lo, hi))
            lb = "".join("█" if bb[i] else "_" for i in range(lo, hi))
            mark = "".join("^" if ab[i] != bb[i] else " " for i in range(lo, hi))
            if mark.strip():
                print(f"D{ch} A {la}\n    B {lb}\n      {mark}")

    # CSV 差异清单
    out = csv_path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "proto_diff_报告.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(["通道", "起始ms", "结束ms", "差异点数"])
        for (ch, cnt, segs) in per:
            for (s, e) in segs:
                wcsv.writerow([f"D{ch}", f"{s * dt * 1000:.3f}",
                               f"{e * dt * 1000:.3f}", e - s])
    print(f"\n差异区间清单已导出: {out}")
    return sim

def main():
    args = [a for a in sys.argv[1:]]
    if len(args) < 2 or args[0].startswith("-"):
        print(__doc__)
        sys.exit(1)
    rate = None
    if "--rate" in args:
        i = args.index("--rate")
        rate = int(args[i + 1])
        del args[i:i + 2]
    csv_path = None
    if "--csv" in args:
        i = args.index("--csv")
        csv_path = args[i + 1]
        del args[i:i + 2]
    run(args[0], args[1], rate, csv_path)

if __name__ == "__main__":
    main()
