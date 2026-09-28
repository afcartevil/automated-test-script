#!/system/bin/sh
# Qualcomm volcano: cpu hotplug stress - toggle cpu1-7 offline/online in a loop.
# Runs in background until next reboot.

while true; do
	for c in 1 2 3 4 5 6 7; do
		echo 0 > /sys/devices/system/cpu/cpu$c/online
	done
	sleep 5
	for c in 1 2 3 4 5 6 7; do
		echo 1 > /sys/devices/system/cpu/cpu$c/online
	done
	sleep 5
done
