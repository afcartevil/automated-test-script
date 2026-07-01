@echo off
cd /d %~dp0
echo Starting xssx...
python start_xssx_python.py %*
echo Done
