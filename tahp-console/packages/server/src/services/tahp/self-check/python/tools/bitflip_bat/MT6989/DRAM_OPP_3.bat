echo "MMDVFS MUST keep lowest voltage (for mt6989)"
adb -s %1 shell "echo 0 4 > /sys/module/mtk_mmdvfs_debug/parameters/force_step"

echo "Fixed UFS  vcore low requirement"
adb -s %1 shell "echo 3 > /sys/devices/platform/soc/112b0000.ufshci/clkscale/clkscale_control"

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

echo "=== disable iSE ==="
adb -s %1 shell "echo disable 1 > /proc/ise"

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "fix vcore 0.600v and dram 3088M"
adb -s %1 shell "echo 13 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"