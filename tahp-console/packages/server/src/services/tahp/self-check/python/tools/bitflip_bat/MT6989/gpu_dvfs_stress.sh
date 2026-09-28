#!/system/bin/sh

# read the gpu dvfs table from gpu_working_opp_table in gpufreqv2
FILENAME_GPU='/proc/gpufreqv2/gpu_working_opp_table'
FILENAME_STACK='/proc/gpufreqv2/stack_working_opp_table'
FILENAME=''

dvfs_table=()
length=0
have_stack_buck=0

if test -f $FILENAME_STACK; then
	FILENAME=$FILENAME_STACK
	have_stack_buck=1
	echo "platform have stack buck, first using stack opp dvfs."
else
	FILENAME=$FILENAME_GPU
	echo "platform have NOT stack buck, using gpu opp dvfs."
fi

IFS=$'\n'
for line in $(cat $FILENAME)
do
	echo $line
	### please check the table to check how to substring.
	dvfs_table[$length]=${line:11:6}
	echo ${dvfs_table[$length]}
	length=$(($length+1))
done

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.05

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%$length))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/kernel/ged/hal/custom_boost_gpu_freq

	echo "fix_opp = $fix_opp, freq = ${dvfs_table[$fix_opp]}"
	
	if [ $have_stack_buck -eq 1 ]; then
		cat /proc/gpufreqv2/gpufreq_status | grep -e STACK.OPP
	else
		cat /proc/gpufreqv2/gpufreq_status | grep -e GPU.OPP
	fi
done