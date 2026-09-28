rem set cpu 6, 7 offline
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu6/online"
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu7/online"
rem check status
adb -s %1 shell "cat /sys/devices/system/cpu/online"
adb -s %1 shell "cat /sys/devices/system/cpu/offline"