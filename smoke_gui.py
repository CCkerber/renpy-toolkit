# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import time

# 定位 venv pythonw 与主程序（相对于本脚本所在项目目录）
_BASE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(_BASE, "venv", "Scripts", "pythonw.exe")
GUI = os.path.join(_BASE, "toolkit_gui.py")

PROC = subprocess.Popen([PYW, GUI], cwd=_BASE)

time.sleep(1.5)

import ctypes
u32 = ctypes.windll.user32
cb = ctypes.create_unicode_buffer(256)

# 找窗口
hwnd = u32.FindWindowW(None, "Ren'Py 工具箱")
if not hwnd:
    PROC.terminate()
    print("FAIL: window not found")
    sys.exit(1)
u32.GetWindowTextW(hwnd, cb, 256)
print(f"found window: {cb.value}")

# 发关闭
u32.PostMessageW(hwnd, 0x0010, 0, 0)

for _ in range(30):
    if PROC.poll() is not None:
        print(f"process exited rc={PROC.returncode}")
        if PROC.returncode == 0:
            print("SMOKE PASSED")
            sys.exit(0)
        sys.exit(1)
    time.sleep(0.5)

print("FAIL: process did not exit")
PROC.terminate()
sys.exit(1)
