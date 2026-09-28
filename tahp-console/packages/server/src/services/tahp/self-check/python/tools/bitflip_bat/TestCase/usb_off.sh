#!/system/bin/sh

#write by yanghui.li@mediatek.com

#stress count
ntest=$1

#sleep duration, default 10s
duration=$2
#try sleep with 5s, each 0.1s, 10times
try_time=5
try_count=$(($try_time*10))


for i in $(seq 1 ${ntest})
do
	#set wake alarm
	echo +$duration > /sys/class/rtc/rtc0/wakealarm
	
	#set wake alarm fail, may have old alarm.
	if [ $? -ne 0 ]; then
		echo +=$duration > /sys/class/rtc/rtc0/wakealarm
	fi
	
	# press powerkey to sleep
	input keyevent 26
	
	# record before sustem wall time.
	before_time=$(cat /sys/class/rtc/rtc0/since_epoch)

	test_prop_value=$(getprop vendor.mediatek.suspend_stress)

	if [ -n $test_prop_value -a $test_prop_value -eq "0" ]; then
		echo "host need abort test !!!"
		input keyevent 26
		sleep 1
		# unlock screen
		input keyevent 82
		break
	fi

	# usb set to off, system will goto suspend.
	setprop vendor.usb.charging yes

	# sleep $try_times s to wait system goto suspend, need using very small pace to try.
	index=0
	interval=0
	while [ $index -lt $try_count ]
	do
		after_time=$(cat /sys/class/rtc/rtc0/since_epoch)
		interval=$(($after_time - $before_time))
		echo interval=$interval, index=$index
		# if wall interval is bigger than real time, may have sleep.
		if [ interval -gt 4 ]; then
			break
		fi
		
		index=$(($index+1))
		sleep 0.1

	done
	
	# press powerkey when system resume
	input keyevent 26
	
	# usb set to on
	setprop vendor.usb.charging no
	
	sleep 1
	
	# unlock screen
	input keyevent 82
	
	# wait usb on 
	sleep 2

done

echo "exit system suspend/resume stress test"
