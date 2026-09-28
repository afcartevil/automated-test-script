:: Qualcomm volcano: online all CPUs (equivalent of MTK Fix_CPU_ALL_ON)
adb -s %1 shell "for c in 1 2 3 4 5 6 7; do echo 1 > /sys/devices/system/cpu/cpu$c/online; done"
adb -s %1 shell "cat /sys/devices/system/cpu/online"
