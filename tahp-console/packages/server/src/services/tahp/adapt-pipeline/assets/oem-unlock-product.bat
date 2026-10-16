@echo off
setlocal EnableExtensions
REM Transsion OEM unlock (userdebug / userroot). Arg1 = adb serial.
set "SERIAL=%~1"
if "%SERIAL%"=="" (
  echo ERROR: missing device serial
  exit /b 1
)

echo [oem-unlock] serial=%SERIAL%
adb -s "%SERIAL%" root
if errorlevel 1 (
  echo ERROR: adb root failed
  exit /b 1
)
adb -s "%SERIAL%" wait-for-device
adb -s "%SERIAL%" shell service call oem_lock 4 i32 1
adb -s "%SERIAL%" reboot bootloader

set /a _n=0
:wait_fastboot
fastboot -s "%SERIAL%" getvar product 1>nul 2>nul
if not errorlevel 1 goto do_unlock
set /a _n+=1
if %_n% GEQ 30 (
  echo ERROR: fastboot device not found
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_fastboot

:do_unlock
fastboot -s "%SERIAL%" oem tran_skip_confirm_key
fastboot -s "%SERIAL%" flashing unlock
if errorlevel 1 (
  echo ERROR: fastboot flashing unlock failed
  exit /b 1
)
fastboot -s "%SERIAL%" erase userdata
fastboot -s "%SERIAL%" reboot

adb -s "%SERIAL%" wait-for-device
adb -s "%SERIAL%" root
adb -s "%SERIAL%" wait-for-device
adb -s "%SERIAL%" shell settings put Global device_provisioned 1
adb -s "%SERIAL%" shell settings put Secure user_setup_complete 1
adb -s "%SERIAL%" shell setprop persist.sys.allow_update_persistent_app 1
adb -s "%SERIAL%" shell setprop persist.debug.dalvik.vm.jdwp.enabled 1
adb -s "%SERIAL%" disable-verity
adb -s "%SERIAL%" reboot
adb -s "%SERIAL%" wait-for-device
echo [oem-unlock] done
exit /b 0
