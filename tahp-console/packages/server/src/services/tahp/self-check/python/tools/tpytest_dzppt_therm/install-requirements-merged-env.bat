@echo off
cd /d %~dp0
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-merged.txt
echo.
pause