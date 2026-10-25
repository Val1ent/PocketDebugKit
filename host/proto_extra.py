#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 扩展协议解码器集
========================================================================
全部沿用 proto_common 的统一接口与 DECKS 注册表，与现有解码器完全兼容：

  1. spi        慢速 SPI（SCK/MOSI/MISO/CS，支持 CPOL/CPHA，MSB 先发）
  2. stepper    步进电机 STEP/DIR（步数、方向、瞬时速度、累计位置）
  3. encoder    正交编码器 A/B/Z（4 倍频计数、转速 RPM、零点复位）
  4. rc5        红外遥控 RC-5（飞利浦 14 位帧：起始/翻转/地址/命令）
  5. ultrasonic HC-SR04 超声波测距（TRIG+ECHO → 距离 cm）
  6. fan        4 线风扇转速（TACH 每圈 2 个脉冲 → RPM）

注意：采样率 10kHz，因此只支持"慢速"总线（≤2kHz 量级），快速协议需提高采样率。
本文件不改固件、不烧录、不触碰任何既有文件。可单独运行自测：
    py -3.12 proto_extra.py
"""
from proto_common import channel_bits, event, register

# ======================================================================
# 1. 慢速 SPI（演示：SCK=1kHz，CPOL=0/CPHA=0，MSB 先发）
# ======================================================================
def decode_spi(samples, rate, sck_ch=2, mosi_ch=3, miso_ch=4, cs_ch=5,
               cpol=0, cpha=0):
    """
    在 CS 有效(低)期间，按采样沿取 MOSI/MISO 各 8 位为一字节（MSB 先发）。
    采样沿规则：CPOL=0 前导沿=上升、CPOL=1 前导沿=下降；
               CPHA=0 在前导沿采样、CPHA=1 在后沿采样。
    """
    sck = channel_bits(samples, sck_ch)
    mosi = channel_bits(samples, mosi_ch)
    miso = channel_bits(samples, miso_ch)
    cs = channel_bits(samples, cs_ch)
    n = len(samples)
    dt = 1.0 / rate
    events = []
    sample_rising = (cpol == cpha)     # CPOL==CPHA 时采样沿为上升沿
    sample_idx = set()
    for i in range(1, n):
        if sample_rising and sck[i - 1] == 0 and sck[i] == 1:
            sample_idx.add(i)
        elif not sample_rising and sck[i - 1] == 1 and sck[i] == 0:
            sample_idx.add(i)

    active = False
    bits_m = []
    bits_s = []
    t_byte = 0.0
    for i in range(n):
        if cs[i] == 0 and not active:
            active = True
            bits_m = []
            bits_s = []
            events.append(event(i * dt, cs_ch, "CS_LOW", "片选拉低，传输开始"))
        elif cs[i] == 1 and active:
            active = False
            events.append(event(i * dt, cs_ch, "CS_HIGH", "片选拉高，传输结束"))
        elif active and i in sample_idx:
            if not bits_m:
                t_byte = i * dt
            bits_m.append(mosi[i])
            bits_s.append(miso[i])
            if len(bits_m) == 8:
                vm = vs = 0
                for b in bits_m:                 # MSB 先发
                    vm = (vm << 1) | b
                for b in bits_s:
                    vs = (vs << 1) | b
                events.append(event(t_byte, sck_ch, "SPI",
                                    f"MOSI=0x{vm:02X} MISO=0x{vs:02X}"))
                bits_m = []
                bits_s = []
    events.sort(key=lambda e: e["t"])
    return events

def make_spi_test(rate):
    """慢速 SPI：CS 拉低 → MOSI 0x3C,0xA5 / MISO 0x11,0x22 → CS 拉高。"""
    n = int(0.06 * rate)
    sck = [1] * n
    mosi = [0] * n
    miso = [0] * n
    cs = [1] * n

    def put(arr, t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            arr[i] = val

    T = 0.001                       # 1kHz 时钟
    half = 0.0005
    t = 0.003
    put(cs, t, t + 0.0165, 0)       # CS 低 16 个时钟 + 余量

    def send(m, s):
        nonlocal t
        for k in range(8):
            bm = (m >> (7 - k)) & 1
            bs = (s >> (7 - k)) & 1
            put(sck, t, t + half, 0)          # SCK 低半周期
            put(mosi, t, t + T, bm)           # 数据在 SCK 低时建立
            put(miso, t, t + T, bs)
            put(sck, t + half, t + T, 1)      # SCK 高半周期（采样沿）
            t += T

    send(0x3C, 0x11)
    send(0xA5, 0x22)
    # 合并：SCK=D2 MOSI=D3 MISO=D4 CS=D5
    return [(sck[i] << 2) | (mosi[i] << 3) | (miso[i] << 4) | (cs[i] << 5)
            for i in range(n)]

register("spi", decode_spi, make_spi_test, "慢速SPI")

# ======================================================================
# 2. 步进电机 STEP/DIR（STEP 上升沿走一步，DIR 高=正转）
# ======================================================================
def decode_stepper(samples, rate, step_ch=0, dir_ch=1):
    """
    STEP 上升沿 = 一步；DIR=1 正转（+1），DIR=0 反转（-1）。
    输出逐步事件（前 20 步 + 此后每 20 步抽样，避免实时刷屏）与
    收尾汇总（总步数/累计位置/换向次数/平均与峰值速度）。
    """
    step = channel_bits(samples, step_ch)
    dirn = channel_bits(samples, dir_ch)
    n = len(samples)
    dt = 1.0 / rate
    events = []
    pos = 0
    steps = 0
    flips = 0
    prev_dir = None
    last_t = None
    speeds = []
    for i in range(1, n):
        if step[i - 1] == 0 and step[i] == 1:
            d = 1 if dirn[i] else 0
            pos += 1 if d else -1
            steps += 1
            t_now = i * dt
            if prev_dir is not None and prev_dir != d:
                flips += 1
            prev_dir = d
            sp_txt = ""
            if last_t is not None and t_now > last_t:
                sp = 1.0 / (t_now - last_t)
                speeds.append(sp)
                sp_txt = f" 速度={sp:.0f}步/s"
            last_t = t_now
            if steps <= 20 or steps % 20 == 0:
                events.append(event(t_now, step_ch, "STEP",
                    f"第{steps}步 方向={'正' if d else '反'} 累计={pos:+d}{sp_txt}"))
    if steps:
        avg = sum(speeds) / len(speeds) if speeds else 0.0
        pk = max(speeds) if speeds else 0.0
        events.append(event((n - 1) * dt, step_ch, "STEP_SUM",
            f"共{steps}步 累计={pos:+d} 换向{flips}次 "
            f"均速={avg:.0f}步/s 峰值={pk:.0f}步/s"))
    events.sort(key=lambda e: e["t"])
    return events

def make_stepper_test(rate):
    """30 步正转 + 10 步反转，步间隔 500us（2kHz 步进），DIR=D1。"""
    n = int(0.06 * rate)
    step = [0] * n
    dirn = [1] * n

    def put(arr, t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            arr[i] = val

    t = 0.005

    def burst(count, d, per=0.0005):
        nonlocal t
        put(dirn, t, t + count * per, d)
        for _ in range(count):
            put(step, t, t + 0.0002, 1)     # 200us 高脉冲
            t += per

    burst(30, 1)                            # 正转 30 步
    burst(10, 0)                            # 反转 10 步
    return [(step[i]) | (dirn[i] << 1) for i in range(n)]

register("stepper", decode_stepper, make_stepper_test, "步进电机STEP/DIR")

# ======================================================================
# 3. 正交编码器 A/B/Z（4 倍频计数，Z 相零点复位）
# ======================================================================
def decode_encoder(samples, rate, a_ch=0, b_ch=1, z_ch=2, ppr=None):
    """
    x4 计数：A/B 每个跳变沿计一次。A 超前 B 为正转。
    z_ch 给出时，Z 相上升沿把位置清零并输出 ZERO 事件（无 Z 相时传 z_ch=None）；
    ppr 给出每转脉冲数时，事件里附带转速 RPM（RPM=沿速/(4*ppr)*60）。
    事件抽样输出（前 30 沿 + 此后每 30 沿），末尾给汇总。
    """
    a = channel_bits(samples, a_ch)
    b = channel_bits(samples, b_ch)
    z = channel_bits(samples, z_ch) if z_ch is not None else None
    n = len(samples)
    if n == 0:
        return []            # 空数据直接返回，保证不崩溃
    dt = 1.0 / rate
    FWD = {(0, 0): (1, 0), (1, 0): (1, 1), (1, 1): (0, 1), (0, 1): (0, 0)}
    REV = {(0, 0): (0, 1), (0, 1): (1, 1), (1, 1): (1, 0), (1, 0): (0, 0)}
    events = []
    pos = 0
    edges_cnt = 0
    last_t = None
    speeds = []
    prev = (a[0], b[0])
    for i in range(1, n):
        if z is not None and z[i - 1] == 0 and z[i] == 1:
            pos = 0
            events.append(event(i * dt, z_ch, "ZERO", "Z相零点 位置复位=0"))
        cur = (a[i], b[i])
        if cur != prev:
            if FWD.get(prev) == cur:
                delta = 1
            elif REV.get(prev) == cur:
                delta = -1
            else:
                delta = 0            # 双相同时跳变（毛刺），忽略
            if delta:
                pos += delta
                edges_cnt += 1
                t_now = i * dt
                if last_t is not None and t_now > last_t:
                    speeds.append(1.0 / (t_now - last_t))
                last_t = t_now
                if edges_cnt <= 30 or edges_cnt % 30 == 0:
                    rpm = ""
                    if ppr and speeds:
                        rpm = (f" 转速="
                               f"{sum(speeds[-30:]) / len(speeds[-30:]) / (ppr * 4) * 60:.0f}RPM")
                    events.append(event(t_now, a_ch, "ENCODER",
                        f"第{edges_cnt}沿 {'正' if delta > 0 else '反'} "
                        f"位置={pos:+d}{rpm}"))
            prev = cur
    if edges_cnt:
        avg = sum(speeds) / len(speeds) if speeds else 0.0
        events.append(event((n - 1) * dt, a_ch, "ENCODER_SUM",
                            f"共{edges_cnt}沿 位置={pos:+d} 平均={avg:.1f}沿/s"))
    events.sort(key=lambda e: e["t"])
    return events

def make_encoder_test(rate):
    """A 超前 B 正转 25 圈周期（100 沿）→ Z 脉冲清零 → 反转 5 周期（20 沿）。"""
    n = int(0.06 * rate)
    a = [0] * n
    b = [0] * n
    z = [0] * n

    def put(arr, t0, t1, val):
        aa = max(0, int(round(t0 * rate)))
        bb = min(n, int(round(t1 * rate)))
        for i in range(aa, bb):
            arr[i] = val

    dur = 0.00025                      # 每个相位 250us
    t = 0.002
    FWD = [(1, 0), (1, 1), (0, 1), (0, 0)]     # A 超前 B
    REV = [(0, 1), (1, 1), (1, 0), (0, 0)]     # B 超前 A

    def cycle(seq):
        nonlocal t
        for (av, bv) in seq:
            put(a, t, t + dur, av)
            put(b, t, t + dur, bv)
            t += dur

    for _ in range(25):
        cycle(FWD)
    put(z, t - dur, t, 1)              # Z 相脉冲（零点复位）
    for _ in range(5):
        cycle(REV)
    return [(a[i]) | (b[i] << 1) | (z[i] << 2) for i in range(n)]

register("encoder", decode_encoder, make_encoder_test, "正交编码器A/B/Z")

# ======================================================================
# 4. 红外遥控 RC-5（飞利浦，14 位帧，双相编码）
# ======================================================================
def decode_rc5(samples, rate, ch=0):
    """
    RC-5：空闲低；每位 1778us，位中点必有跳变（双相编码）：
      前半高+后半低 = 逻辑 1，前半低+后半高 = 逻辑 0。
    帧 = 起始 1,1 + 翻转位 + 5 位地址 + 6 位命令（MSB 先发）。
    逐候选起点做 14 位结构校验（每位的 1/4 与 3/4 处电平必须相反），
    只接受前两位为 1 的帧，避免半位错位误报。
    """
    bits = channel_bits(samples, ch)
    n = len(bits)
    dt = 1.0 / rate
    events = []
    full = 1778e-6                      # 每位 1.778ms
    rises = [i for i in range(1, n) if bits[i - 1] == 0 and bits[i] == 1]
    used = set()
    for s in rises:
        if s in used:
            continue
        frame = []
        ok = True
        for k in range(14):
            q1 = int(round(s + (k + 0.25) * full * rate))
            q3 = int(round(s + (k + 0.75) * full * rate))
            if q1 >= n or q3 >= n:
                ok = False
                break
            l1, l3 = bits[q1], bits[q3]
            if l1 == l3:                 # 位中点必须有跳变
                ok = False
                break
            frame.append(l1)             # 前半高=1，前半低=0
        if ok and frame[0] == 1 and frame[1] == 1:
            toggle = frame[2]
            addr = 0
            for b in frame[3:8]:
                addr = (addr << 1) | b
            cmd = 0
            for b in frame[8:14]:
                cmd = (cmd << 1) | b
            events.append(event(s * dt, ch, "RC5",
                                f"地址={addr} 命令={cmd} 翻转位={toggle}"))
            end_i = int(round(s + 14 * full * rate))
            for r in rises:              # 帧内候选点不再重复检测
                if s < r < end_i:
                    used.add(r)
    events.sort(key=lambda e: e["t"])
    return events

def make_rc5_test(rate):
    """一帧 RC-5：起始 1,1 + 翻转 0 + 地址 0b00101(5) + 命令 0b100001(33)。"""
    half = 889e-6
    frame = [1, 1, 0] + [0, 0, 1, 0, 1] + [1, 0, 0, 0, 0, 1]
    n = int((0.010 + 14 * 2 * half + 0.010) * rate)
    bits = [0] * n

    def put(t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            bits[i] = val

    t = 0.010
    for bit in frame:
        put(t, t + half, bit)                    # 前半 = 位值
        put(t + half, t + 2 * half, 1 - bit)     # 后半反相（位中点跳变）
        t += 2 * half
    return bits[:]

register("rc5", decode_rc5, make_rc5_test, "红外RC-5")

# ======================================================================
# 5. HC-SR04 超声波测距（TRIG 触发，ECHO 高电平时间 → 距离）
# ======================================================================
def decode_ultrasonic(samples, rate, trig_ch=0, echo_ch=1):
    """
    TRIG 上升沿 = 一次测量开始；随后 ECHO 高电平时间 = 回波时间。
    距离 cm = 回波秒 * 340m/s / 2 * 100。量程 100us~50ms（约 1.7cm~8.5m）。
    """
    trig = channel_bits(samples, trig_ch)
    echo = channel_bits(samples, echo_ch)
    n = len(samples)
    dt = 1.0 / rate
    events = []
    i = 0
    while i < n - 1:
        if trig[i] == 0 and trig[i + 1] == 1:
            tr = i + 1
            events.append(event(tr * dt, trig_ch, "TRIG", "触发脉冲"))
            er = None
            j = tr
            while j < n - 1:                       # 找 ECHO 上升沿
                if echo[j] == 0 and echo[j + 1] == 1:
                    er = j + 1
                    break
                j += 1
            if er is not None:
                ef = n
                j = er
                while j < n - 1:                   # 找 ECHO 下降沿
                    if echo[j] == 1 and echo[j + 1] == 0:
                        ef = j + 1
                        break
                    j += 1
                dur = (ef - er) * dt
                cm = dur * 340.0 / 2.0 * 100.0
                if 0.0001 <= dur <= 0.05:
                    events.append(event(er * dt, echo_ch, "DISTANCE",
                                        f"回波={dur * 1e6:.0f}us 距离≈{cm:.1f}cm"))
                else:
                    events.append(event(er * dt, echo_ch, "DIST_ERR",
                                        f"回波={dur * 1e6:.0f}us 超出量程"))
                i = er
            else:
                i = tr
            continue
        i += 1
    events.sort(key=lambda e: e["t"])
    return events

def make_ultrasonic_test(rate):
    """两次测量：回波 1.0ms→≈17.0cm；回波 1.5ms→≈25.5cm（声速 340m/s）。"""
    n = int(0.05 * rate)
    trig = [0] * n
    echo = [0] * n

    def put(arr, t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            arr[i] = val

    put(trig, 0.003, 0.0031, 1)
    put(echo, 0.004, 0.005, 1)          # 1.0ms 回波 → 17.0cm
    put(trig, 0.030, 0.0301, 1)
    put(echo, 0.031, 0.0325, 1)         # 1.5ms 回波 → 25.5cm
    return [(trig[i]) | (echo[i] << 1) for i in range(n)]

register("ultrasonic", decode_ultrasonic, make_ultrasonic_test, "超声测距HC-SR04")

# ======================================================================
# 6. 4 线风扇转速（TACH 每圈 2 个脉冲，下降沿间隔 → RPM）
# ======================================================================
def decode_fan(samples, rate, tach_ch=0, pulses_per_rev=2):
    """
    TACH 每转输出 pulses_per_rev（默认 2）个脉冲；下降沿间隔 = 半圈时间。
    RPM = 60 / (间隔秒 * 每转脉冲数)。每攒满 5 个间隔输出一次滑动平均，
    末尾输出整体平均/最低/最高。
    """
    tach = channel_bits(samples, tach_ch)
    n = len(samples)
    dt = 1.0 / rate
    falls = [i for i in range(1, n) if tach[i - 1] == 1 and tach[i] == 0]
    events = []
    win = []
    for k in range(len(falls) - 1):
        per = (falls[k + 1] - falls[k]) * dt
        if not (0.0001 <= per <= 1.0):      # 忽略异常间隔
            continue
        win.append(per)
        if len(win) > 5:
            win.pop(0)
        if len(win) == 5:
            rpms = [60.0 / (p * pulses_per_rev) for p in win]
            events.append(event(falls[k] * dt, tach_ch, "FAN",
                                f"转速≈{sum(rpms) / len(rpms):.0f}RPM"))
    if win:
        rpms = [60.0 / (p * pulses_per_rev) for p in win]
        events.append(event((n - 1) * dt, tach_ch, "FAN_SUM",
            f"平均={sum(rpms) / len(rpms):.0f}RPM "
            f"最低={min(rpms):.0f} 最高={max(rpms):.0f}"))
    events.sort(key=lambda e: e["t"])
    return events

def make_fan_test(rate):
    """3000RPM 风扇：2 脉冲/圈 → 100 脉冲/s → 脉冲周期 10ms，共 20 个脉冲。"""
    n = int(0.25 * rate)
    tach = [0] * n

    def put(arr, t0, t1, val):
        a = max(0, int(round(t0 * rate)))
        b = min(n, int(round(t1 * rate)))
        for i in range(a, b):
            arr[i] = val

    t = 0.010
    period = 0.010                      # 10ms = 3000RPM×2脉冲/圈
    for _ in range(20):
        put(tach, t, t + period / 2, 1)  # 50% 占空比
        t += period
    return tach[:]

register("fan", decode_fan, make_fan_test, "风扇转速TACH")

# ======================================================================
if __name__ == "__main__":
    from proto_common import DECKS, selftest, print_events
    print("已登记解码器:", list(DECKS.keys()))
    for name in DECKS:
        print("\n" + "=" * 60)
        print("自测:", name, "-", DECKS[name]["desc"])
        ev, _ = selftest(name)
        print_events(ev)
