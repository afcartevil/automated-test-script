@echo off
@setlocal enabledelayedexpansion

set cpu_dvfs_exist=unknown

for /F %%I in ('adb -s %1 shell ls /proc/cpuhvfs/cpufreq_debug') do (
   set cpu_dvfs_exist=%%I
)

echo avoid thermal reboot, we reduce the frequency every once in a while.

if "!cpu_dvfs_exist!" EQU "/proc/cpuhvfs/cpufreq_debug" (
	echo find cpuhvfs, using cpuhvfs to control cpu dvfs stress.
	@echo on
	adb -s %1 push cpudvfs_hilo_opp0_opp15_test.sh /data/local/tmp/cpudvfs_hilo_opp0_opp15_test.sh
	adb -s %1 shell chmod 755 /data/local/tmp/cpudvfs_hilo_opp0_opp15_test.sh
	adb -s %1 shell sh /data/local/tmp/cpudvfs_hilo_opp0_opp15_test.sh
	@echo off
) else (
	echo NOT find cpuhvfs, using linux native cmd to control cpu dvfs stress.
	@echo on
	adb -s %1 push cpudvfs_native_opp0_opp15_test.sh /data/local/tmp/cpudvfs_native_opp0_opp15_test.sh
	adb -s %1 shell chmod 755 /data/local/tmp/cpudvfs_native_opp0_opp15_test.sh
	adb -s %1 shell sh /data/local/tmp/cpudvfs_native_opp0_opp15_test.sh
	@echo off
)