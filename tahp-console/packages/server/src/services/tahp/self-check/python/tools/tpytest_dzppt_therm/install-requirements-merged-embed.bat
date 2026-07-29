@echo off
cd /d %~dp0
..\tpytest-python-embed\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-merged.txt
echo.
pause