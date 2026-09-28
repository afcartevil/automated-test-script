@echo off
@setlocal enabledelayedexpansion
rem get the devices list, and call BitflipAnalysisTool.jar
for /F %%I in ('adb devices') do (
   set device=%%I
   if "!device!" NEQ "List" (
		echo "bitflip start test !device!"
		start run_mulit_force_test_all.bat !device!
   )
)

@endlocal

pause