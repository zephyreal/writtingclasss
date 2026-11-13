@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 local_function_test.py
if errorlevel 1 echo 请安装 Python 3.12；也可在终端运行 python local_function_test.py 查看错误。
pause
