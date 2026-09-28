:: Qualcomm variant: reduced memory footprint (fixed 1536M instead of %3=half of total).
:: Reason: volcano device MemAvailable is only ~2.5GB; 3840M + GPU stress triggers
:: extreme direct reclaim and the vendor memory guard reboots the phone (observed 2026-09-28).
:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push stressapptest%2 /data/local/tmp/stressapptest
adb -s %1 shell chmod 755 /data/local/tmp/stressapptest

@echo off
SET /A all_cpu=%4
SET /A m_cpu=%all_cpu%
SET /A i_cpu=%all_cpu%/2
SET /A c_cpu=%all_cpu%/2

@echo all_cpu=%all_cpu%,m_cpu=%m_cpu%,i_cpu=%i_cpu%,c_cpu=%c_cpu%

@echo on
adb -s %1 shell "am start -n com.android.gpu_emulation_stress_test/.MainActivity --ez stress true --ei glesApiLevel 2 --ei numObjects 2000"
adb -s %1 shell /data/local/tmp/stressapptest -s 180 -M 1536 -m %m_cpu%
adb -s %1 shell "am start -a android.intent.action.MAIN -c android.intent.category.HOME"
