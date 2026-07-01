@echo off

set team=xttx
set scheme=xssx

cd /d %~dp0
echo Starting env %scheme%...
python --version
if errorlevel 1 (
echo Error: system env python.exe not found.
pause
goto :eof)
python launchers\%team%\%scheme%\start_%scheme%_gui_python.py %*
echo Done
