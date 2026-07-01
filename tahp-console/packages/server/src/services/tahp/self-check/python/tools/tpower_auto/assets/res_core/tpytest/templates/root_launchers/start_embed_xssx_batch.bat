@echo off

set team=xttx
set scheme=xssx

cd /d %~dp0
echo Starting embed %scheme% batch...
..\tpytest-python-embed\python.exe --version
if errorlevel 1 (
echo Error: "..\tpytest-python-embed\python.exe" not found.
pause
goto :eof)
..\tpytest-python-embed\python.exe launchers\%team%\%scheme%\start_%scheme%_batch_python.py %*
echo Done
