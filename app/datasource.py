# -*- coding: utf-8 -*-
"""数据源：串口枚举、串口单次采集、采集文件打开。

采集数据格式与 host/ 侧一致：
  rate    : int，采样率 Hz
  samples : list[int]，每个 int 是一个采样时刻的 8 通道快照（1 字节），
            bit0 = D0，bit7 = D7。
"""
import os
import time

from app_paths import ensure_host_path

ensure_host_path()

import proto_io  # noqa: E402
import serial  # noqa: E402
from serial.tools import list_ports  # noqa: E402

SERIAL_RATE = 10000


def list_serial_ports():
    """返回可用串口列表 [(设备名, 描述), ...]。"""
    return [(p.device, p.description) for p in list_ports.comports()]


def acquire_serial(port, n_points, timeout=8.0):
    """从指定串口单次采集恰好 n_points 个字节。

    打开串口后置 DTR/RTS，短暂等待并清空输入缓冲，随后非阻塞轮询，
    累计读到 n_points 个字节或超时为止；结束（含异常）时关闭串口。
    超时未读满时抛出带排查建议的异常。
    """
    ser = serial.Serial(port, 115200, timeout=0)
    ser.dtr = True
    ser.rts = True
    try:
        time.sleep(0.5)
        ser.reset_input_buffer()
        data = bytearray()
        deadline = time.monotonic() + timeout
        while len(data) < n_points and time.monotonic() < deadline:
            pending = ser.in_waiting
            if pending:
                data.extend(ser.read(min(pending, n_points - len(data))))
            else:
                time.sleep(0.01)
    finally:
        ser.close()
    if len(data) < n_points:
        raise RuntimeError(
            f"采集超时：实际收到 {len(data)} 点，需要 {n_points} 点。\n"
            "请检查：是否选择了 CH32 数据口（底部 USB-FS 口而非调试口）、"
            "A15 是否环回到 D0、该串口是否被其他程序占用，然后重试。"
        )
    return SERIAL_RATE, list(data)


def acquire_file(path):
    """读取 .sr / .bin 采集文件，返回 (rate, samples)。

    .sr 为 sigrok 压缩包（采样率从 metadata 读取）；
    .bin 为原始 8 通道字节流（采样率按固件值 10000 Hz）。
    其他扩展名或读取失败时抛出带可读信息的异常。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".sr", ".bin"):
        raise ValueError(
            f"不支持的文件类型：{ext or '（无扩展名）'}。请选择 .sr 或 .bin 文件。"
        )
    try:
        if ext == ".sr":
            rate, samples = proto_io.read_sr(path)
        else:
            rate, samples = proto_io.read_bin(path, SERIAL_RATE)
    except Exception as exc:
        raise ValueError(f"无法读取文件 {path}：{exc}") from exc
    if rate is None:
        raise ValueError(f"无法读取文件 {path}：文件中缺少采样率信息。")
    return rate, list(samples)
