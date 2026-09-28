:: Qualcomm volcano: GPU auto DVFS (default devfreq range, kgsl drives freq by load)
adb -s %1 shell "echo 264000000 > /sys/class/kgsl/kgsl-3d0/devfreq/min_freq"
adb -s %1 shell "echo 1150000000 > /sys/class/kgsl/kgsl-3d0/devfreq/max_freq"
adb -s %1 shell "cat /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq"
