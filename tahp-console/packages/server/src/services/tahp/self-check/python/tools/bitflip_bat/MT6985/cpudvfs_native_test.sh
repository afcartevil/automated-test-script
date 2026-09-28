#!/system/bin/sh

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.02

### 1. disable thermal controller
/vendor/bin/thermal_intf apply disable_throttling.conf

### 2. disable mediatek powerhal need reboot, now we block system permissions to control dvfs
# setprop persist.vendor.powerhal.enable 0
chown root.root /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq
chown root.root /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
chown root.root /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq
chown root.root /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq

### 3. disable mediatek fpsgo
echo 0 > /sys/kernel/fpsgo/common/force_onoff

### get cpufreq policy from /sys/devices/system/cpu/cpufreq.
### how many policy, and which tables.
policys=()
policy_length=0

### dvfs tables, it is a 2D array.
dvfs_tables=()

### get all policy
for line in $(ls /sys/devices/system/cpu/cpufreq | awk {'print $1'})
do
	policys[$policy_length]=$line
	policy_length=$(($policy_length+1))
done

### get all dvfs table in policys
index=0
for policy in ${policys[@]}
do
	temp_table=()
	temp_length=0
	for line in $(cat /sys/devices/system/cpu/cpufreq/$policy/scaling_available_frequencies)
	do
		temp_table[$temp_length]=$line
		temp_length=$(($temp_length+1))
	done
	echo table[$index]=${temp_table[@]}
	dvfs_tables[$index]=${temp_table[@]}
	index=$(($index+1))
done


### test in dead loop
while [ 1 ]
do

	sleep $T_DVFS_INTERVAL
	
	policy_index=0
	for policy in ${policys[@]}
	do
		dvfs_table=(${dvfs_tables[$policy_index]})
		
		if [ ${#dvfs_table[@]} -ne 0 ]; then
			dvfs_opp=$((${RANDOM}%${#dvfs_table[@]}))
		
			echo ${dvfs_table[$dvfs_opp]} > /sys/devices/system/cpu/cpufreq/$policy/scaling_min_freq
			echo ${dvfs_table[$dvfs_opp]} > /sys/devices/system/cpu/cpufreq/$policy/scaling_max_freq

			echo dvfs_table=$policy_index,dvfs_opp=$dvfs_opp,define_freq=${dvfs_table[$dvfs_opp]},actual_freq=$(cat /sys/devices/system/cpu/cpufreq/$policy/scaling_cur_freq)
		fi
		
		policy_index=$(($policy_index+1))
	done

done

echo "warning: we have exit dvfs stress, and recovery thermal, dvfs permission, fpsgo."

### 1. enable thermal controller
/vendor/bin/thermal_intf apply thermal.conf

### 2. we recovery system permissions to control dvfs
# setprop persist.vendor.powerhal.enable 0
chown system.system /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq
chown system.system /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
chown system.system /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq
chown system.system /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq

### 3. recovery mediatek fpsgo
echo 1 > /sys/kernel/fpsgo/common/force_onoff