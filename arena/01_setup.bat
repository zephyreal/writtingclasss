@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r arena\requirements.txt
if errorlevel 1 goto fail
echo 完成。请阅读上方结果。
pause
exit /b 0
:fail
echo 操作未完成，请根据README排查上方错误。
pause
exit /b 1
