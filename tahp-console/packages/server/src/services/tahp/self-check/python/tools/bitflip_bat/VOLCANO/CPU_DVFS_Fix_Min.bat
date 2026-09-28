:: Qualcomm volcano: pin all CPU policies to min frequency (equivalent of MTK Fix-OPP15)
:: lower max first, then min (max cannot go below current min)
adb -s %1 shell "echo performance > /sys/devices/system/cpu/cpufreq/policy0/scaling_governor"
adb -s %1 shell "echo performance > /sys/devices/system/cpu/cpufreq/policy4/scaling_governor"
adb -s %1 shell "echo performance > /sys/devices/system/cpu/cpufreq/policy7/scaling_governor"
adb -s %1 shell "echo 441600 > /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
adb -s %1 shell "echo 480000 > /sys/devices/system/cpu/cpufreq/policy4/scaling_max_freq"
adb -s %1 shell "echo 480000 > /sys/devices/system/cpu/cpufreq/policy7/scaling_max_freq"
adb -s %1 shell "echo 441600 > /sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq"
adb -s %1 shell "echo 480000 > /sys/devices/system/cpu/cpufreq/policy4/scaling_min_freq"
adb -s %1 shell "echo 480000 > /sys/devices/system/cpu/cpufreq/policy7/scaling_min_freq"
adb -s %1 shell "cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq /sys/devices/system/cpu/cpufreq/policy7/scaling_cur_freq"
