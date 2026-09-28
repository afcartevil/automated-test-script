rem set cpu2, 3, 4, 5 offline
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu2/online"
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu3/online"
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu4/online"
adb -s %1 shell "echo 0 > /sys/devices/system/cpu/cpu5/online"
rem check status
adb -s %1 shell "cat /sys/devices/system/cpu/online"
adb -s %1 shell "cat /sys/devices/system/cpu/offline"