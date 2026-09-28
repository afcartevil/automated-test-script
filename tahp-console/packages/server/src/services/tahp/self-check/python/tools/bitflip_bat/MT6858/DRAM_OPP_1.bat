echo "MMDVFS MUST keep lowest voltage (for mt6858)"
adb -s %1 shell "echo 3 > /sys/module/mtk_mmdvfs/parameters/force_step"
adb -s %1 shell "echo 0 3 > /sys/module/mtk_mmdvfs_debug/parameters/force_step"

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "fix vcore 0.650v and dram 4266M"
adb -s %1 shell "echo 2 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"