echo "MMDVFS MUST keep lowest voltage (for mt6993)"
adb -s %1 shell "echo 0 5 > /sys/module/mtk_mmdvfs_debug/parameters/force_step"

echo "Fixed UFS  vcore low requirement"
adb -s %1 shell "echo 3 >  /sys/devices/platform/soc/16810000.ufshci/clkscale/clkscale_control"

adb -s %1 shell "settings put secure location_mode 0"

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

::echo "no need disable iSE, iSE eat VLP/vcore_sram voltage"
::adb -s %1 shell "echo disable 1 > /proc/ise"

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "fix vcore 0.725, emi 633m, enhance fdvfsc stress"
adb -s %1 shell "echo 14 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"