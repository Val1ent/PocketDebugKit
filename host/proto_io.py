#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 采集文件共享读写
====================================================
供 proto_browser / proto_diff / proto_stats 复用的只读小工具：
  read_sr(path)        读取 sigrok .sr 压缩包 -> (rate, samples)
  read_bin(path, rate) 读取原始 8 通道字节流 -> (rate, samples)
纯标准库、只读、不改固件。
"""
import zipfile

def parse_rate_str(s):
    """'10 kHz' / '1 MHz' / '1000' 之类的字符串 → 采样率 Hz 数值。"""
    s = str(s).strip().lower()
    num = ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            break
    if not num:
        return None
    val = float(num)
    if "mhz" in s:
        val *= 1e6
    elif "khz" in s:
        val *= 1e3
    return int(round(val))

def read_sr(path):
    """读取 sigrok .sr 压缩包（capture3.py 的输出格式）→ (rate, samples)。"""
    with zipfile.ZipFile(path) as z:
        meta = z.read("metadata").decode("utf-8", "replace")
        rate = None
        for line in meta.splitlines():
            line = line.strip()
            if line.startswith("samplerate="):
                rate = parse_rate_str(line.split("=", 1)[1])
        data = z.read("logic-1")
    return rate, list(data)

def read_bin(path, rate):
    """读取原始 8 通道字节流 → (rate, samples)。"""
    with open(path, "rb") as f:
        data = f.read()
    return rate, list(data)
