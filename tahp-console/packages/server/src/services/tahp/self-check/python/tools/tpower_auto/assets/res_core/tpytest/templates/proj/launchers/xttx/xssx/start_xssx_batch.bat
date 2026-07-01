@echo off
cd /d %~dp0
echo Starting xssx batch...
python start_xssx_batch_python.py %*
echo Done
