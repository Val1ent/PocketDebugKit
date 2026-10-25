# -*- coding: utf-8 -*-
"""把 host/ 目录加入 sys.path，供 app/ 内各模块 import 复用接口。

host/ 与 app/ 同级。所有对 host/ 下模块（proto_common、proto_io、
analyzer、measure 等）的 import 都必须在本文件的 ensure_host_path()
调用之后进行。
"""
import os
import sys


def ensure_host_path():
    """计算 host/ 的绝对路径，若不在 sys.path 中则插入到 sys.path[0]。"""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    host_dir = os.path.join(os.path.dirname(app_dir), "host")
    if host_dir not in sys.path:
        sys.path.insert(0, host_dir)
    return host_dir
