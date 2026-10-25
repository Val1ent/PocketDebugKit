#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口袋数字调试助手 - 综合协议实验室
==================================================
把"基础 3 协议（NEC/舵机/慢速I2C）+ 扩展 6 协议（SPI/步进/编码器/RC-5/超声/风扇）"
装进一个入口，全部沿用 proto_common 的统一接口与 DECKS 注册表：

  [1] 全量离线自检报告：跑每个解码器自带测试波形并核对预期事件，
      打印 PASS/FAIL 验收报告 —— 无需硬件、零烧录，赛前演练/验收用
  [2] 单个协议离线演示：任意解码器自带测试波形
  [3] 实时串口解码：底部 USB-FS 口采集实时解码（含全部 9 个协议）
  [4] 导出全部事件 CSV（Excel 可直接打开）
  [5] PPM 多通道扩展验证：验证舵机解码器的 PPM 分支（8 通道帧）

用法： py -3.12 proto_lab.py
批处理（供脚本/验收调用）：
      py -3.12 proto_lab.py --selftest   只跑全量自检
      py -3.12 proto_lab.py --ppm        只跑 PPM 扩展验证
      py -3.12 proto_lab.py --export     只导出事件 CSV
"""
import os, sys, time, csv
from collections import deque
import proto_common
import proto_decoders          # noqa: F401  基础：NEC/舵机/慢速I2C
import proto_extra             # noqa: F401  扩展：SPI/步进/编码器/RC-5/超声/风扇
from proto_common import DECKS, print_events, build_wave

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

SAMPLE_RATE = 10000
WINDOW = 3000

# ---- 验收规则：自测事件里必须出现的（类型, 关键内容） ----
REQUIRED = {
    "nec":        [("LEADER", None), ("NEC", "地址=0x00 命令=0x45"), ("REPEAT", None)],
    "servo":      [("SERVO", "角度=0.0°"), ("SERVO", "角度=90.0°"),
                   ("SERVO", "角度=180.0°")],
    "i2c":        [("START", None), ("ADDR", "0x48 W ACK"),
                   ("DATA", "0x55 ACK"), ("STOP", None)],
    "spi":        [("CS_LOW", None), ("SPI", "MOSI=0x3C MISO=0x11"),
                   ("SPI", "MOSI=0xA5 MISO=0x22"), ("CS_HIGH", None)],
    "stepper":    [("STEP", "第1步"), ("STEP_SUM", "共40步"), ("STEP_SUM", "累计=+20")],
    "encoder":    [("ENCODER", None), ("ZERO", None)],
    "rc5":        [("RC5", "地址=5 命令=33")],
    "ultrasonic": [("TRIG", None), ("DISTANCE", "距离≈17.0cm"),
                   ("DISTANCE", "距离≈25.5cm")],
    "fan":        [("FAN", None), ("FAN_SUM", "平均=3000RPM")],
}
FORBIDDEN = {
    "nec": [("NEC_ERR", None)],        # NEC 校验错误一条都不能有
}

def check_deck(name, events):
    """按 REQUIRED/FORBIDDEN 核对事件，返回 (ok, 问题列表)。"""
    problems = []
    for typ, sub in REQUIRED.get(name, []):
        hits = [e for e in events if e["type"] == typ
                and (sub is None or sub in e["text"])]
        if not hits:
            problems.append(f"缺 {typ} {sub or ''}".strip())
    for typ, sub in FORBIDDEN.get(name, []):
        hits = [e for e in events if e["type"] == typ
                and (sub is None or sub in e["text"])]
        if hits:
            problems.append(f"出现禁止项 {typ} x{len(hits)}")
    return (len(problems) == 0), problems

def report_all():
    """跑全部 9 个解码器自测并核对预期，打印验收报告。返回是否全部通过。"""
    print("=" * 64)
    print("全量协议自检报告（纯离线 · 零烧录 · 可重复验收）")
    print("=" * 64)
    passed = 0
    total = 0
    for name, deck in DECKS.items():
        total += 1
        try:
            samples = deck["make"](SAMPLE_RATE)
            events = deck["decode"](samples, SAMPLE_RATE)
            ok, problems = check_deck(name, events)
        except Exception as exc:
            ok, problems, events = False, [f"异常: {exc}"], []
        if ok:
            passed += 1
        print(f"\n[{'PASS' if ok else 'FAIL'}] {name:<10} {deck['desc']}"
              f"  事件 {len(events)} 条")
        for p in problems:
            print("        问题: " + p)
        for e in events[:5]:
            print(f"        {e['t']*1000:8.3f}ms  {e['type']:<10} {e['text']}")
        if len(events) > 5:
            print(f"        ... 其余 {len(events)-5} 条略")
    print("\n" + "=" * 64)
    print(f"验收结果: {passed}/{total} 通过" + ("  [OK]" if passed == total else "  [FAIL]"))
    return passed == total

def make_ppm_test(rate):
    """PPM 演示：8 通道，间隔依次 1000~1800us，帧同步 >4000us。"""
    n = int(0.06 * rate)
    pulses = []
    t = 0.003
    for us in (1000, 1200, 1400, 1600, 1800, 1500, 1300, 1100):
        pulses.append((t, 1, 0.0004))       # 400us 通道脉冲
        t += us / 1e6
    pulses.append((t, 1, 0.0004))           # 帧尾短脉冲，凑出第 8 个通道值
    return build_wave(0, pulses, rate, n, idle=0)

def check_ppm():
    """验证 decode_servo 的 PPM 分支：8 通道帧且不误报 SERVO。"""
    samples = make_ppm_test(SAMPLE_RATE)
    events = proto_decoders.decode_servo(samples, SAMPLE_RATE, ch=0)
    ppm = [e for e in events if e["type"] == "PPM"]
    servos = [e for e in events if e["type"] == "SERVO"]
    ok = len(ppm) == 1 and "8通道" in ppm[0]["text"] and not servos
    print("=" * 64)
    print(f"[{'PASS' if ok else 'FAIL'}] PPM 多通道扩展验证")
    for e in events:
        print(f"  {e['t']*1000:9.3f} ms  D{e['ch']}  {e['type']:<10} {e['text']}")
    print("说明: 帧内 8 个通道间隔被识别为 PPM，且未误报成 SERVO（间隔≠20ms）。")
    return ok

def pick_port():
    ports = list(list_ports.comports())
    print("===== 检测到的串口 =====")
    for i, p in enumerate(ports):
        print(f"  [{i}]  {p.device}   {p.description}")
    sel = input("选择【底部 USB-FS 口】序号: ").strip()
    return ports[int(sel)].device

def pick_decoder():
    names = list(DECKS.keys())
    print("===== 可选协议解码器（基础3 + 扩展6）=====")
    for i, n in enumerate(names):
        print(f"  [{i}]  {n:<10} {DECKS[n]['desc']}")
    sel = input("选择解码器序号: ").strip()
    return names[int(sel)]

def offline_demo(name):
    print(f"\n===== 离线演示：{name}（自带测试波形，无需硬件）=====")
    samples = DECKS[name]["make"](SAMPLE_RATE)
    events = DECKS[name]["decode"](samples, SAMPLE_RATE)
    print_events(events)
    print(f"\n（共 {len(samples)} 个采样点，{len(events)} 个事件）")

def live_mode(name):
    if serial is None:
        print("缺少 pyserial: py -3.12 -m pip install pyserial")
        return
    port = pick_port()
    ser = serial.Serial(port, 115200, timeout=0)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.5)
    ser.reset_input_buffer()
    raw = deque(maxlen=WINDOW)
    shown = set()               # 已打印事件去重
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

def export_csv():
    """把全部解码器自测事件导出为 CSV（utf-8-sig，Excel 可直接打开）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "proto_lab_events.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["解码器", "类型", "时间ms", "通道", "内容"])
        for name in DECKS:
            samples = DECKS[name]["make"](SAMPLE_RATE)
            for e in DECKS[name]["decode"](samples, SAMPLE_RATE):
                w.writerow([name, e["type"], f"{e['t']*1000:.3f}",
                            f"D{e['ch']}", e["text"]])
    print("已导出:", path)

def main():
    print("===== 口袋数字调试助手 · 综合协议实验室 =====")
    print("  [1] 全量离线自检报告（无需硬件 · 零烧录 · 验收用）")
    print("  [2] 单个协议离线演示（自带测试波形）")
    print("  [3] 实时串口解码（需硬件：底部 USB-FS 口）")
    print("  [4] 导出全部事件 CSV")
    print("  [5] PPM 多通道扩展验证")
    sel = input("选择: ").strip()
    if sel == "1":
        sys.exit(0 if report_all() else 1)
    elif sel == "2":
        offline_demo(pick_decoder())
    elif sel == "3":
        live_mode(pick_decoder())
    elif sel == "4":
        export_csv()
    elif sel == "5":
        sys.exit(0 if check_ppm() else 1)
    else:
        print("无效选择")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if report_all() else 1)
    if "--ppm" in sys.argv:
        sys.exit(0 if check_ppm() else 1)
    if "--export" in sys.argv:
        export_csv()
        sys.exit(0)
    main()
