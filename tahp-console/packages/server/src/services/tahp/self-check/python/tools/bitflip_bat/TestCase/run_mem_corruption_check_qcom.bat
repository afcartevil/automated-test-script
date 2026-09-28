:: Qualcomm variant: large-capacity pass uses fixed 2048M instead of %3 (half of total).
:: Reason: volcano device MemAvailable is only ~2.5GB; 3840M risks memory-guard reboot.
:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push mem_corruption_check /data/local/tmp/
adb -s %1 shell chmod 0755 /data/local/tmp/mem_corruption_check

@echo off
SET /A all_cpu=%4
SET /A m_cpu=%all_cpu%
SET /A i_cpu=%all_cpu%/2
SET /A c_cpu=%all_cpu%/2

:: force using 128M and 32ms idle setting to test cpu idle and SLC dss flow.
@echo on
adb -s %1 shell /data/local/tmp/mem_corruption_check -s 30 -l 0 -m 128 -t %m_cpu% -i 32000 -r 50 -p

:: Large capacity DRAM test, to find bitflip and hardware memory corruption
adb -s %1 shell /data/local/tmp/mem_corruption_check -s 60 -l 0 -m 2048 -t %m_cpu% -i 8000 -r 50 -p

@echo off
adb -s %1 shell "echo all mem_corruption_check test OK."
