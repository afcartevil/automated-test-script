@echo off
@setlocal enabledelayedexpansion

set cpu_dvfs_exist=unknown

for /F %%I in ('adb -s %1 shell ls /proc/cpuhvfs/cpufreq_debug') do (
   set cpu_dvfs_exist=%%I
)

if "!cpu_dvfs_exist!" EQU "/proc/cpuhvfs/cpufreq_debug" (
	@echo Set DSU high frequency so that CPU output high bandwidth
	adb -s %1 shell "echo 1900000 > /proc/cpuhvfs/dsu_ctrl_freq_send"
	adb -s %1 shell "echo 3 > /proc/cpuhvfs/dsu_ctrl_mode"
)

@echo force setting opp 0
adb -s %1 shell "echo 0 > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp"