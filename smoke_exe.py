# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import time
import ctypes

# 定位打包后的 exe：优先桌面 RenPyToolkit 目录，其次项目 dist 目录
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(_BASE, "RenPyToolkit", "RenPyToolkit.exe")
if not os.path.exists(EXE):
    EXE = os.path.join(_BASE, "dist", "RenPyToolkit", "RenPyToolkit.exe")
proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
time.sleep(2)
u32 = ctypes.windll.user32
hwnd = u32.FindWindowW(None, "Ren'Py 工具箱")
if not hwnd:
    proc.terminate()
    print("FAIL: window not found")
    sys.exit(1)
u32.PostMessageW(hwnd, 0x0010, 0, 0)
for _ in range(30):
    if proc.poll() is not None:
        print(f"exited rc={proc.returncode}")
        print("EXE SMOKE PASSED" if proc.returncode == 0 else "FAIL")
        sys.exit(0 if proc.returncode == 0 else 1)
    time.sleep(0.5)
print("FAIL: did not exit")
proc.terminate()
sys.exit(1)
