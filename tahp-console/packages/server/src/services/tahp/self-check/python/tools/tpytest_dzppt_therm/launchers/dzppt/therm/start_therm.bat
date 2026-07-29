@echo off
cd /d %~dp0
echo Starting therm...
python start_therm_python.py %*
echo Done
