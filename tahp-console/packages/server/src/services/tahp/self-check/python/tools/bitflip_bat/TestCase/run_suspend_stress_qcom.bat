:: Qualcomm variant of run_suspend_stress.bat (uses usb_off_qcom.sh).
:: NOTE: adb disconnects during the test by design; device restores USB after each wake.
:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push usb_off_qcom.sh /data/local/tmp/
adb -s %1 shell chmod 755 /data/local/tmp/usb_off_qcom.sh

@echo off
@setlocal enabledelayedexpansion
echo suspend stress need usb off, the adb will auto disconnect!

set /A ntest=5
set /A duration=6
rem  not only suspend, but also resume and usb on cost.
set /A total=%ntest% * (%duration% + 10)

set zygote_boot_before=unknown
set zygote_boot_after=unknown

for /F %%I in ('adb -s %1 shell getprop ro.boottime.zygote') do (
   set zygote_boot_before=%%I
)

echo zygote_boottime_before=!zygote_boot_before!

adb -s %1 shell date

@echo on

adb -s %1 shell "nohup sh -c '/data/local/tmp/usb_off_qcom.sh %ntest% %duration%' > /data/local/tmp/suspend_test.txt 2>&1"

@echo off
echo sleep %total%s to wait phone resume
ping -n %total% 127.0.0.1>nul

echo very small probability suspend timeout, now mandatory wait-for-device %1
adb -s %1 wait-for-device

adb -s %1 shell date

for /F %%I in ('adb -s %1 shell getprop ro.boottime.zygote') do (
   set zygote_boot_after=%%I
)

echo zygote_boottime_after=!zygote_boot_after!

if "!zygote_boot_before!" EQU "!zygote_boot_after!" (
	echo suspend stress test pass.
) else (
	echo suspend stress test fail, system abnormal reboot.
)

@endlocal
