#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 多协议解码公共框架
========================================
不依赖任何第三方库（纯标准库），不碰固件、不烧录。

【采样数据格式（务必遵守）】
  samples : list[int]，每个 int 是一个采样时刻的 8 通道快照（1 字节）
            bit0 = D0(PD0)，bit1 = D1(PD1)，...，bit7 = D7(PD7)
            即某通道电平 = (sample >> ch) & 1
  rate    : int，采样率 Hz（当前 10000）

【统一事件格式 Event】
  dict: {"t": float(秒), "ch": int(通道), "type": str(类型), "text": str(可读文本)}
  解码器必须返回 list[Event]，并按 t 升序。

【解码器约定】
  每个解码器提供两个函数：
    decode_XXX(samples, rate, **通道参数) -> list[Event]
    make_XXX_test(rate) -> list[int]      # 生成已知内容的 8 通道测试样本
  并在 DECKS 里登记（见文件末尾示例）。
"""
import sys
from functools import reduce

# 当本文件作为主脚本运行时，把自身也注册为 "proto_common"，
# 避免解码器执行 `from proto_common import ...` 时重复导入导致注册表不同步。
if __name__ == "__main__":
    sys.modules.setdefault("proto_common", sys.modules[__name__])

# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def channel_bits(samples, ch):
    """把 8 通道快照样本展开成某一通道的 0/1 序列。"""
    mask = 1 << ch
    return [1 if (b & mask) else 0 for b in samples]

def edges_of(bits):
    """返回电平跳变沿列表：[(index, new_level), ...]（含初始电平）。"""
    out = []
    if not bits:
        return out
    out.append((0, bits[0]))
    for i in range(1, len(bits)):
        if bits[i] != bits[i - 1]:
            out.append((i, bits[i]))
    return out

def pulse_widths(bits, rate):
    """把单通道序列切成连续电平段：[(start_index, level, 宽度_秒), ...]。"""
    dt = 1.0 / rate
    segs = []
    start = 0
    for i in range(1, len(bits)):
        if bits[i] != bits[start]:
            segs.append((start, bits[start], (i - start) * dt))
            start = i
    segs.append((start, bits[start], (len(bits) - start) * dt))
    return segs

def event(t, ch, typ, text):
    """构造统一事件。"""
    return {"t": float(t), "ch": int(ch), "type": str(typ), "text": str(text)}

def merge_events(*lists):
    """合并多路事件并按时间排序。"""
    out = []
    for L in lists:
        out.extend(L)
    out.sort(key=lambda e: e["t"])
    return out

def set_channel(samples, idx, ch, level):
    """在 samples[idx] 上设置某通道电平（用于生成测试波形）。"""
    if level:
        samples[idx] |= (1 << ch)
    else:
        samples[idx] &= ~(1 << ch) & 0xFF

def build_wave(ch, pulses, rate, n, idle=1):
    """
    生成 8 通道测试波形（其余通道为 0）。
    pulses: [(起始秒, 电平, 时长秒), ...]，按时间顺序；空闲为 idle。
    """
    samples = [0] * n
    # 先铺空闲电平
    for i in range(n):
        set_channel(samples, i, ch, idle)
    for (t0, lvl, dur) in pulses:
        a = int(round(t0 * rate))
        b = int(round((t0 + dur) * rate))
        for i in range(max(0, a), min(n, b)):
            set_channel(samples, i, ch, lvl)
    return samples

# ----------------------------------------------------------------------
# 注册表与自测
# ----------------------------------------------------------------------
DECKS = {}   # name -> {"decode": fn, "make": fn, "desc": str}

def register(name, decode_fn, make_fn, desc=""):
    DECKS[name] = {"decode": decode_fn, "make": make_fn, "desc": desc}

def print_events(events, ch_name=None):
    """终端打印事件。"""
    if not events:
        print("  (未解码出任何事件)")
    for e in events:
        c = ch_name if ch_name is not None else e["ch"]
        print(f"  {e['t']*1000:9.3f} ms  D{c}  {e['type']:<10} {e['text']}")

def selftest(name):
    """对某个解码器跑自带测试波形，返回 (事件, 样本)。"""
    deck = DECKS[name]
    samples = deck["make"](10000)
    events = deck["decode"](samples, 10000)
    return events, samples

# 导入各解码器，若不存在则忽略
try:
    import proto_decoders          # noqa: F401
except ImportError:
    proto_decoders = None

if __name__ == "__main__":
    print("已登记解码器:", list(DECKS.keys()))
    for name in DECKS:
        print("\n" + "=" * 60)
        print("自测:", name, "-", DECKS[name]["desc"])
        ev, _ = selftest(name)
        print_events(ev)
