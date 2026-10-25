#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 多协议解码器
================================
已实现：红外遥控 NEC、舵机 PWM/PPM、慢速 I2C。
"""
from proto_common import (channel_bits, edges_of, pulse_widths, event,
                         build_wave, register)

# ======================================================================
# 红外遥控 NEC（低电平有效）
# ======================================================================
def _us(w):
    return w * 1_000_000.0

def decode_nec(samples, rate, ch=0):
    bits = channel_bits(samples, ch)
    segs = pulse_widths(bits, rate)          # [(start, level, width_s), ...]
    dt = 1.0 / rate
    events = []
    i = 0
    n = len(segs)
    while i < n:
        start, lvl, w = segs[i]
        # 引导/重复码都以 7~11ms 低电平开头
        if lvl == 0 and _us(w) >= 7000 and _us(w) <= 11000:
            lead_t = start * dt
            if i + 1 < n:
                _, lvl2, w2 = segs[i + 1]
                us2 = _us(w2)
                if lvl2 == 1 and 3500 <= us2 <= 5500:
                    # ---- 引导码，读 32 位 ----
                    events.append(event(lead_t, ch, "LEADER", "NEC引导码"))
                    bits32 = []
                    j = i + 2
                    # 每位 = 低(560us) + 高(数据)
                    while len(bits32) < 32 and j + 1 < n:
                        sl, ll, wl = segs[j]      # 低段
                        sh, lh, wh = segs[j + 1]  # 高段
                        if ll == 0 and lh == 1 and 350 <= _us(wl) <= 800:
                            hu = _us(wh)
                            if 350 <= hu <= 800:
                                bits32.append(0)
                            elif 1300 <= hu <= 2000:
                                bits32.append(1)
                            else:
                                break
                            j += 2
                        else:
                            break
                    if len(bits32) == 32:
                        def take(off):
                            v = 0
                            for b in range(8):       # LSB 先发
                                if bits32[off + b]:
                                    v |= (1 << b)
                            return v
                        addr = take(0)
                        addr_n = take(8)
                        cmd = take(16)
                        cmd_n = take(24)
                        t = (start) * dt
                        if (addr ^ addr_n) == 0xFF and (cmd ^ cmd_n) == 0xFF:
                            events.append(event(t, ch, "NEC",
                                f"地址=0x{addr:02X} 命令=0x{cmd:02X}"))
                        else:
                            events.append(event(t, ch, "NEC_ERR",
                                f"校验失败 addr=0x{addr:02X}/0x{addr_n:02X} "
                                f"cmd=0x{cmd:02X}/0x{cmd_n:02X}"))
                        i = j
                        continue
                elif lvl2 == 1 and 1800 <= us2 <= 2800:
                    # ---- 重复码 ----
                    events.append(event(start * dt, ch, "REPEAT",
                                        "NEC重复码"))
                    i += 2
                    continue
        i += 1
    events.sort(key=lambda e: e["t"])
    return events

def make_nec_test(rate):
    n = int(0.09 * rate)        # 90ms
    pulses = []
    t = 0.010                   # 10ms 空闲
    # 引导码
    pulses.append((t, 0, 0.009)); t += 0.009
    pulses.append((t, 1, 0.0045)); t += 0.0045
    # 地址 0x00（8 个 0）、地址反码 0xFF（8 个 1）
    seq = []
    seq += [0] * 8                       # 地址 0x00
    seq += [1] * 8                       # 地址反码 0xFF
    # 命令 0x45 = 0b01000101，LSB 先发
    cmd = 0x45
    cmd_bits = [(cmd >> b) & 1 for b in range(8)]
    seq += cmd_bits
    seq += [(~((cmd >> b) & 1)) & 1 for b in range(8)]
    for b in seq:
        pulses.append((t, 0, 0.000560)); t += 0.000560
        pulses.append((t, 1, 0.000560 if b == 0 else 0.001690))
        t += (0.000560 if b == 0 else 0.001690)
    # 结束低脉冲
    pulses.append((t, 0, 0.000560)); t += 0.000560
    # 重复码（再隔约 10ms）
    t += 0.010
    pulses.append((t, 0, 0.009)); t += 0.009
    pulses.append((t, 1, 0.00225)); t += 0.00225
    pulses.append((t, 0, 0.000560)); t += 0.000560
    return build_wave(0, pulses, rate, max(n, int(t * rate) + 10), idle=1)

register("nec", decode_nec, make_nec_test, "红外遥控NEC")

# ======================================================================
# 舵机 PWM / PPM（同一条线：20ms 周期单舵机 PWM 或 多通道 PPM 帧）
# ======================================================================
def decode_servo(samples, rate, ch=0):
    """
    识别两类信号：
      A. 标准舵机 PWM：周期 18~22ms、脉宽 500~2500us，
         角度 = (脉宽us - 1000) / 1000 * 180，结果钳制在 0~180。
      B. PPM 多通道帧：帧内相邻上升沿间隔 = 通道值（500~4000us），
         帧间隔（同步）> 4000us；一帧 >= 4 个通道才输出 PPM。
    """
    bits = channel_bits(samples, ch)
    n = len(bits)
    dt = 1.0 / rate
    edges = edges_of(bits)
    # 只取真实跳变沿（去掉 edges_of 附带的初始电平点）
    rising = [i for (i, lvl) in edges if lvl == 1 and i > 0]
    falling = [i for (i, lvl) in edges if lvl == 0 and i > 0]
    events = []

    # ---- A. 标准舵机 PWM：上升沿到下一个上升沿 = 一个完整周期 ----
    for i in range(len(rising) - 1):
        a, b = rising[i], rising[i + 1]
        per_us = (b - a) * 1e6 / rate
        if 18000.0 <= per_us <= 22000.0:            # 18~22ms 合法周期
            pw_us = None
            for f in falling:                        # 周期内的下降沿 = 脉宽
                if a < f < b:
                    pw_us = (f - a) * 1e6 / rate
                    break
            if pw_us is not None and 500.0 <= pw_us <= 2500.0:
                ang = (pw_us - 1000.0) / 1000.0 * 180.0
                if ang < 0.0:
                    ang = 0.0
                elif ang > 180.0:
                    ang = 180.0
                events.append(event(a * dt, ch, "SERVO",
                                    f"脉宽={pw_us:.0f}us 角度={ang:.1f}°"))

    # ---- B. PPM：相邻上升沿 500~4000us 为通道值，>4000us 为帧同步 ----
    frame = []          # 当前帧内的上升沿索引

    def flush_ppm():
        gaps = []
        for k in range(len(frame) - 1):
            g_us = (frame[k + 1] - frame[k]) * 1e6 / rate
            if 500.0 <= g_us <= 4000.0:
                gaps.append(g_us)
        if len(gaps) >= 4:
            vals = ",".join(f"{g:.0f}" for g in gaps)
            events.append(event(frame[0] * dt, ch, "PPM",
                                f"{len(gaps)}通道: [{vals}]"))

    for r in rising:
        if frame and (r - frame[-1]) * 1e6 / rate > 4000.0:
            flush_ppm()
            frame = []
        frame.append(r)
    flush_ppm()

    events.sort(key=lambda e: e["t"])
    return events

def make_servo_test(rate):
    """
    3 个 20ms 舵机周期：脉宽 1000/1500/2000us → 0°/90°/180°；
    第 4 个脉冲用于凑出第 3 个完整周期（上升沿到下一个上升沿）。
    """
    n = int(0.09 * rate)            # 90ms
    pulses = [
        (0.005, 1, 0.0010),         # 1000us → 0°
        (0.025, 1, 0.0015),         # 1500us → 90°
        (0.045, 1, 0.0020),         # 2000us → 180°
        (0.065, 1, 0.0020),         # 补第 4 个上升沿，凑出第 3 个完整周期
    ]
    return build_wave(0, pulses, rate, n, idle=0)

register("servo", decode_servo, make_servo_test, "舵机PWM/PPM")

# ======================================================================
# 慢速 I2C（SCL=D1，SDA=D0；空闲 SCL=1、SDA=1；MSB 先发，9 位一组）
# ======================================================================
def decode_i2c(samples, rate, scl_ch=1, sda_ch=0):
    """
    慢速 I2C 解码（10kHz 采样适合 SCL<=1kHz）：
      START/STOP：SCL 为高时 SDA 跳变（1->0 起始，0->1 停止）；
      数据：在 SCL 上升沿采样 SDA，每 9 位一组（8 数据 MSB 先 + ACK）；
      第一组 = 7 位从机地址 + R/W（0=写 W，1=读 R），ACK 位 0=ACK、1=NACK。
    """
    scl = channel_bits(samples, scl_ch)
    sda = channel_bits(samples, sda_ch)
    n = len(samples)
    dt = 1.0 / rate
    marks = []                                   # (索引, 类型, SDA采样值)
    for i in range(1, n):                        # 总线条件：SCL 高时 SDA 跳变
        if sda[i] != sda[i - 1] and scl[i] == 1:
            marks.append((i, "STOP" if sda[i] == 1 else "START", None))
    for i in range(1, n):                        # 数据采样点：SCL 上升沿
        if scl[i - 1] == 0 and scl[i] == 1:
            marks.append((i, "SCLK", sda[i]))
    marks.sort(key=lambda m: (m[0], m[1] != "SCLK"))   # 同采样点先处理总线条件

    events = []
    in_trans = False
    bits = []
    t_byte = 0.0
    first_byte = True
    for idx, kind, val in marks:
        if kind == "START":
            in_trans = True
            bits = []
            first_byte = True
            events.append(event(idx * dt, sda_ch, "START", "起始条件"))
        elif kind == "STOP":
            if in_trans:
                events.append(event(idx * dt, sda_ch, "STOP", "停止条件"))
            in_trans = False
            bits = []
        elif in_trans:
            if not bits:
                t_byte = idx * dt                  # 本字节首 bit 时刻
            bits.append(val)
            if len(bits) == 9:
                val8 = 0
                for b in bits[:8]:                 # MSB 先发
                    val8 = (val8 << 1) | b
                ack = "ACK" if bits[8] == 0 else "NACK"
                if first_byte:
                    addr = val8 >> 1               # 高 7 位为从机地址
                    rw = "R" if (val8 & 1) else "W"
                    events.append(event(t_byte, sda_ch, "ADDR",
                                        f"0x{addr:02X} {rw} {ack}"))
                    first_byte = False
                else:
                    events.append(event(t_byte, sda_ch, "DATA",
                                        f"0x{val8:02X} {ack}"))
                bits = []
    events.sort(key=lambda e: e["t"])
    return events

def make_i2c_test(rate):
    """
    慢速 I2C 写传输：START → 地址 0x48+W（=0x90，ACK）→ 数据 0x55（ACK）→ STOP。
    SCL 周期 1000us（1kHz，10kHz 采样下高/低半周期各 5 个采样点）。
    SDA 用 D0（sda_ch=0），SCL 用 D1（scl_ch=1），按位或合并互不覆盖。
    """
    n = int(0.05 * rate)            # 50ms
    scl = [1] * n                   # 空闲 SCL=1
    sda = [1] * n                   # 空闲 SDA=1
    T = 0.001                       # 1000us 时钟周期
    half = 0.0005

    def put(arr, t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            arr[i] = val

    def send_byte(value, ack=0):
        nonlocal t
        data = [(value >> (7 - b)) & 1 for b in range(8)]
        for b in data:
            put(scl, t, t + half, 0)        # SCL 低半周期
            put(sda, t, t + T, b)           # SDA 在 SCL 低时建立
            put(scl, t + half, t + T, 1)    # SCL 高半周期（采样点）
            t += T
        put(scl, t, t + half, 0)            # 第 9 个时钟：ACK 位
        put(sda, t, t + T, ack)
        put(scl, t + half, t + T, 1)
        t += T

    t = 0.002
    put(sda, t, t + 0.0004, 0)              # START：SCL 高时 SDA 高->低
    t += 0.0004
    send_byte(0x90)                         # 地址 0x48 + W(0)
    send_byte(0x55)                         # 数据 0x55
    put(sda, t, t + 0.0004, 1)              # STOP：SCL 高时 SDA 低->高

    # 合并两通道：SDA=D0，SCL=D1
    return [(scl[i] << 1) | sda[i] for i in range(n)]

register("i2c", decode_i2c, make_i2c_test, "慢速I2C")

if __name__ == "__main__":
    from proto_common import DECKS, selftest, print_events
    for name in DECKS:
        print("\n" + "=" * 60)
        print("自测:", name, "-", DECKS[name]["desc"])
        ev, _ = selftest(name)
        print_events(ev)
