@echo off
cd /d "%~dp0"
.xpu_venv\Scripts\python.exe apps/gradio_xpu.py

pause