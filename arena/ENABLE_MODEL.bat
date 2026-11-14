@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe enable_model.py
if errorlevel 1 goto failed
echo 已启用进阶示例，请运行START.bat。
pause
exit /b 0
:failed
echo 启用失败，请查看上方提示。原agent.py保留。
pause
exit /b 1
