@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
cd /d "%~dp0"
".\venv\Scripts\pythonw.exe" toolkit_gui.py
if errorlevel 1 (
  echo [ERROR] GUI failed, retrying with console to show error...
  ".\venv\Scripts\python.exe" toolkit_gui.py
  pause
)
