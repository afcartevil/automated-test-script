echo "MMDVFS MUST keep lowest voltage (for mt6879)"
adb -s %1 shell "echo 3 > /sys/module/mtk_mmdvfs/parameters/force_step"

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

echo "Disable hold vcore whenever UFS access storage"
REM adb -s %1 shell "echo 0 > /proc/ufs_perf"

echo "Let SCP in low freq"
REM adb -s %1 shell "echo opp 0 > /proc/scp_dvfs/scp_dvfs_ctrl"

echo "Let APU in low freq"
adb -s %1 shell "echo 3 5 5 5 5 > /sys/module/apu_top/parameters/aputop_func_sel"

echo "Fix GPU  vcore low requirement"
adb -s %1 shell "echo set 1 30 -1 > /proc/gpufreqv2/limit_table"

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "fix vcore 0.55v and dram 2133M"
adb -s %1 shell "echo 9 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"