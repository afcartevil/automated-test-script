adb devices

rem disable deepidle
adb -s %1 shell "echo 0 > /proc/mtk_lpm/lpm/rc/syspll/enable"

rem disable sodi sodi3
adb -s %1 shell "echo 0 > /proc/mtk_lpm/lpm/rc/bus26m/enable"
adb -s %1 shell "echo 0 > /proc/mtk_lpm/lpm/rc/dram/enable"

rem disable suspend
adb -s %1 shell "echo test > /sys/power/wake_lock"

rem disable mcdi
adb -s %1 shell "echo 0 > /proc/mtk_lpm/cpuidle/enable"

rem disable dcm
adb -s %1 shell "echo disable 0xffff > /sys/dcm/dcm_state"

rem check low power ide state

rem Count of constraint enter:
adb -s %1 shell "cat /proc/mtk_lpm/lpm/rc/state"

rem State of constraint bus26m:
adb -s %1 shell "cat /proc/mtk_lpm/lpm/rc/bus26m/state"

rem State of constraint syspll:
adb -s %1 shell "cat /proc/mtk_lpm/lpm/rc/syspll/state"

rem State of constraint dram:
adb -s %1 shell "cat /proc/mtk_lpm/lpm/rc/dram/state"
