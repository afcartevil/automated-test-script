:: Qualcomm volcano: pin GPU to max frequency (governor has only msm-adreno-tz, pin via min_freq)
adb -s %1 shell "echo 1150000000 > /sys/class/kgsl/kgsl-3d0/devfreq/max_freq"
adb -s %1 shell "echo 1150000000 > /sys/class/kgsl/kgsl-3d0/devfreq/min_freq"
adb -s %1 shell "cat /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq"
