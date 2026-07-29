@echo off
cd /d %~dp0
echo Starting therm batch...
python start_therm_batch_python.py %*
echo Done
