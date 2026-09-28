#!/system/bin/sh

ntest=3000000
delay=0.3	## 300ms
all_on_delay=0.05 ## 50ms

cpu_num=8
cpus=()

for i in $(seq 1 ${ntest})
do
	#FF to flag echo cpu core.
	test=$(($RANDOM%(1<<$cpu_num)))
	
	if [ $test -gt 0 ]; then
		off_count=0
		for cpu in $(seq 1 ${cpu_num})
		do
			index=$(($cpu-1))
			mask=$((1<<$index))
			value=$(($test&$mask))
			if [ $value -eq 0 -a $off_count -lt 5 ]; then
				echo 0 > /sys/devices/system/cpu/cpu${index}/online
				cpus[$index]=0
				off_count=$(($off_count+1))
			else 
				echo 1 > /sys/devices/system/cpu/cpu${index}/online
				cpus[$index]=1
			fi
		done
		
		echo "off=${off_count} cpu0=${cpus[0]}, cpu1=${cpus[1]}, cpu2=${cpus[2]}, cpu3=${cpus[3]}, cpu4=${cpus[4]}, cpu5=${cpus[5]}, cpu6=${cpus[6]}, cpu7=${cpus[7]}"

		sleep ${delay}
		
		##let all cpu on.
		##avoid spcecial case: cpu 0 on, cpu 1 on, cpu 2 on and other cpu off; next time cpu 0 off, cpu 1 off, then only one cpu on case.
		for cpu in $(seq 1 ${cpu_num})
		do
			index=$(($cpu-1))
			echo 1 > /sys/devices/system/cpu/cpu${index}/online
		done
		
		sleep ${all_on_delay}
	
	fi

done

echo "The test is done and PASS if no exception occurred."
