echo "MMDVFS MUST keep lowest voltage (for mt6789)"
adb -s %1 shell "echo 3 > /sys/module/mtk_mmdvfs/parameters/force_step"

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

echo "Disable hold vcore whenever UFS access storage"
REM adb -s %1 shell "echo 0 > /proc/ufs_perf"

echo "Let SCP in low freq"
adb -s %1 shell "echo opp 0 > /proc/scp_dvfs/scp_dvfs_ctrl"

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "fix vcore 0.55v and dram 2133M"
adb -s %1 shell "echo 9 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"