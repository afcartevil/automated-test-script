@echo off

set team=dzppt
set scheme=current_analysis

cd /d %~dp0
echo Starting env %scheme%...
python --version
if errorlevel 1 (
echo Error: system env python.exe not found.
pause
goto :eof)
python launchers\%team%\%scheme%\start_%scheme%_python.py %*
echo Done
