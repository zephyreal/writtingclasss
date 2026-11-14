@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe local_function_test.py
) else (
  py -3.12 local_function_test.py
)
if errorlevel 1 echo 请检查上方错误；基础版需要Python 3.12，模型版请先运行ENABLE_MODEL.bat。
pause
