:: Qualcomm volcano: enable all cpuidle states (state1/state2; state0=WFI always kept on)
adb -s %1 shell "for c in 0 1 2 3 4 5 6 7; do echo 0 > /sys/devices/system/cpu/cpu$c/cpuidle/state1/disable; echo 0 > /sys/devices/system/cpu/cpu$c/cpuidle/state2/disable; done"
adb -s %1 shell "cat /sys/devices/system/cpu/cpu0/cpuidle/state1/disable /sys/devices/system/cpu/cpu0/cpuidle/state2/disable"
