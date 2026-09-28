:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push run_apu_vcore_test.sh /data/local/tmp/run_apu_vcore_test.sh
adb -s %1 shell chmod 755 /data/local/tmp/run_apu_vcore_test.sh

echo Start test apu vcore test...
adb -s %1 shell sh /data/local/tmp/run_apu_vcore_test.sh

@echo off
setlocal enabledelayedexpansion
for /f "tokens=1-4 delims=/- " %%a in ('date /t') do (
    set year=%%a
    set month=%%b
    set day=%%c
)
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (
    set hour=%%a
    set minute=%%b
)
set second=%time:~6,2%
set timestamp=%year%%month%%day%_%hour%%minute%%second%
set dirname=%5\apu_vcore_stress\%timestamp%

mkdir %dirname%

@echo on
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_edpa_c0.txt %dirname%
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_edpa_c1.txt %dirname%
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_result_c1.txt %dirname%
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_result_c2.txt %dirname%
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_result_c4.txt %dirname%
adb -s %1 pull /data/local/tmp/apu_vcore_test/test_result_c8.txt %dirname%