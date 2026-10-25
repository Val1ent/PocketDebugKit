#!/usr/bin/env python3
# CH32H417 逻辑分析仪 - USB CDC 采集 v3
# 关键修复：非阻塞轮询 in_waiting，绕开 Windows CDC 阻塞式 read 卡死；显式 DTR/RTS
import os, sys, time, zipfile
from collections import Counter

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("缺少 pyserial: python -m pip install pyserial")
    input("回车退出..."); sys.exit(1)

POINTS   = 3000
RATE_STR = "10 kHz"

def write_sr(path, data):
    metadata = (
        "[global]\nsigrok version=0.7.2\n\n[device 1]\n"
        "capturefile=logic-1\n"
        "total probes=8\n"
        f"samplerate={RATE_STR}\n"
        "total analog=0\n"
        "probe1=D0\nprobe2=D1\nprobe3=D2\nprobe4=D3\n"
        "probe5=D4\nprobe6=D5\nprobe7=D6\nprobe8=D7\n"
        "unitsize=1\n"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("version", "2")
        z.writestr("metadata", metadata)
        z.writestr("logic-1", bytes(data))

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    while True:
        ports = list(list_ports.comports())
        print("\n===== 检测到的串口 =====")
        for i, p in enumerate(ports):
            print(f"  [{i}]  {p.device}   {p.description}")
        sel = input("选择【底部 USB-FS 口】序号(回车重扫, q退出): ").strip()
        if sel.lower() == 'q': break
        if sel == '': continue
        try:
            port = ports[int(sel)].device
        except Exception:
            print("序号无效"); continue

        try:
            ser = serial.Serial(port, 115200, timeout=0)  # timeout=0 非阻塞
            ser.dtr = True      # 显式通知设备主机已连接
            ser.rts = True
        except Exception as e:
            print("打开串口失败(关掉串口助手再试):", e); continue

        print("2 秒后开始采集，请确认 A15 已接到 D0 ...")
        time.sleep(2)
        ser.reset_input_buffer()
        print(f"正在从 {port} 采集 {POINTS} 点 ...")

        data = b""
        t0 = time.time(); last_diag = 0
        while len(data) < POINTS and (time.time() - t0) < 10:
            n = ser.in_waiting           # 缓冲区现有字节数，不阻塞
            if n:
                n = min(n, POINTS - len(data))   # 精确读到 POINTS，不多读积压
                data += ser.read(n)      # 非阻塞读，立即返回
                print(f"  已收到 {len(data)}/{POINTS} (本批 {n})")
            else:
                time.sleep(0.02)
                if time.time() - last_diag > 1:
                    last_diag = time.time()
                    print(f"  等待中... in_waiting=0, 已收 {len(data)}, 已等 {time.time()-t0:.0f}s")
        ser.close()

        print(f"共收到 {len(data)} 字节，用时 {time.time()-t0:.1f}s")
        if len(data) == POINTS:
            top = Counter(data).most_common(5)
            print("最常见字节:", [(hex(k), v) for k, v in top])
            fn = os.path.join(base, f"capture_{int(time.time())}.sr")
            write_sr(fn, data)
            print("已生成:", fn)
        else:
            print("数据不足。")
            print("- 若一直 in_waiting=0：设备没往这口发，确认选的是 USB-FS(COM4)、A15->D0 接好、串口助手已关闭；")
            print("- 可拔插底部 USB 线、按 RESET 后重选端口再试。")

        if input("\n回车再采一屏，q 退出: ").strip().lower() == 'q':
            break

if __name__ == "__main__":
    main()
