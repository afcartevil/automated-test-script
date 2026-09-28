:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push mtk_mem_test /data/local/tmp/
adb -s %1 shell chmod 0755 /data/local/tmp/mtk_mem_test

@echo off
SET /A all_cpu=%4
SET /A m_cpu=%all_cpu%
SET /A i_cpu=%all_cpu%/2
SET /A c_cpu=%all_cpu%/2

:: force using 64M and 16ms idle setting to test cpu idle and SLC dss flow.
@echo on
adb -s %1 shell /data/local/tmp/mtk_mem_test -s 30 -l 0 -m 64 -t %c_cpu% -i 16000

:: Large capacity DRAM test, to find bitflip and hardware memory corruption
adb -s %1 shell /data/local/tmp/mtk_mem_test -s 60 -l 0 -m 2048 -t %m_cpu% -i 0

:: force using 128M and 16ms idle setting to test cpu idle and SLC dss flow.
adb -s %1 shell /data/local/tmp/mtk_mem_test -s 30 -l 0 -m 128 -t %m_cpu% -i 16000

:: Large capacity DRAM test, to find bitflip and hardware memory corruption
adb -s %1 shell /data/local/tmp/mtk_mem_test -s 60 -l 0 -m 2048 -t %m_cpu% -i 0

@echo off
adb -s %1 shell "echo all mtk_mem_test test OK."