#!/system/bin/sh
# Qualcomm variant of usb_off.sh: suspend/resume stress without adb.
# USB is cut via sys.usb.config (saved and restored). Runs fully on device.

ntest=$1
duration=$2

# save current usb config to restore it after each wake
old_usb_config=$(getprop sys.usb.config)
if [ -z "$old_usb_config" ]; then
	old_usb_config="adb"
fi

for i in $(seq 1 ${ntest})
do
	# set wake alarm
	echo +$duration > /sys/class/rtc/rtc0/wakealarm
	if [ $? -ne 0 ]; then
		echo +=$duration > /sys/class/rtc/rtc0/wakealarm
	fi

	# press powerkey to screen off
	input keyevent 26

	# usb off, adb disconnects
	setprop sys.usb.config none
	sleep 2

	# real suspend to RAM, wake by rtc alarm
	echo mem > /sys/power/state

	# ---- device wakes here ----
	# usb back on
	setprop sys.usb.config $old_usb_config

	# press powerkey when system resume
	input keyevent 26
	sleep 1
	# unlock screen
	input keyevent 82
	# wait usb on
	sleep 3
done

echo "exit system suspend/resume stress test"
