@echo off
REM 安装 SPN 看板每日检查：每天 09:00 拉取远程数据，满 30 单起桌面通知
setlocal
set PYTHONPATH=%LOCALAPPDATA%\harness\npm-venv\1.3.0\Lib\site-packages
set PYTHONIOENCODING=utf-8
"%LOCALAPPDATA%\harness\npm-venv\1.3.0\Scripts\python.exe" "%~dp0spn_dashboard_cli.py" --json install-daily --time 09:00
echo.
echo 手动检查一次:
"%LOCALAPPDATA%\harness\npm-venv\1.3.0\Scripts\python.exe" "%~dp0spn_dashboard_cli.py" check --min-total 30
pause
