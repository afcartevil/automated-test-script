rem set cpu all online
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu0/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu1/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu2/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu3/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu4/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu5/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu6/online"
adb -s %1 shell "echo 1 > /sys/devices/system/cpu/cpu7/online"
rem check status
adb -s %1 shell "cat /sys/devices/system/cpu/online"
adb -s %1 shell "cat /sys/devices/system/cpu/offline"