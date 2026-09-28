:: only setup once when tool start.
@setlocal enabledelayedexpansion
adb -s %1 install cpu-idle-test.apk
adb -s %1 install gpu-stress.apk
adb -s %1 shell rm -r -f /data/local/tmp/stressapptest
adb -s %1 shell setprop persist.vendor.dbg.anrflow 1
adb -s %1 shell locksettings set-disabled true

:: because dconfig can not record old cmd, MUST set only once.
@echo off
set old_dconfig_cmd=unknown
set display_60_cmd=unknown

for /F "delims=" %%I in ('adb -s %1 shell "dconfig status | grep \"Activate\" | awk {'print $2'} | xargs echo $1"') do (
   set old_dconfig_cmd=%%I
)
for /F %%I in ('adb -s %1 shell "dconfig list | grep \"switch fps to 60\" | awk {'print $1'}"') do (
   set display_60_cmd=%%I
)

if "!display_60_cmd!" NEQ "unknown" (
	if "!old_dconfig_cmd!" EQU "unknown" (
		echo no old dconfig cmd set.
		adb -s %1 shell dconfig set !display_60_cmd! 
	) else (
		echo old_dconfig_cmd=!old_dconfig_cmd!
		echo dconfig set !old_dconfig_cmd! !display_60_cmd!
		adb -s %1 shell dconfig set !old_dconfig_cmd! !display_60_cmd! 
	)
) else (
	echo no display_60_cmd dconfig cmd. 
)


@echo on
adb -s %1 shell "settings put system peak_refresh_rate 60"
adb -s %1 shell "settings put system min_refresh_rate 60"
adb -s %1 shell "dumpsys display | egrep 'mActiveModeId|DisplayModeRecord'" 
rem android s need set this system prop to mount debugfs
adb -s %1 shell "setprop persist.dbg.keep_debugfs_mounted true"

adb -s %1 shell setprop persist.vendor.usb.vcore_boost 0
