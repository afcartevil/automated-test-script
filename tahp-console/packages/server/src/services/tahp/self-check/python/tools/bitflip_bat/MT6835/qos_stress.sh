#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.05

echo " ***** STARTING DVFS STRESS ***** "

#MMDVFS MUST keep lowest voltage (for mt6835)
echo 3 > /sys/module/mtk_mmdvfs/parameters/force_step

#Disable hold vcore whenever UFS access storage
#mt6983 NOT need setting.
#echo 0 > /proc/ufs_perf

#Let SCP in low freq, using vlp buck, ignore
echo opp 0 > /proc/scp_dvfs/scp_dvfs_ctrl

#Let APU in low freq, first need mount debugfs in android S
echo 3 5 5 5 5 > /sys/module/apu_top/parameters/aputop_func_sel

#Fix GPU vcore low requirement
echo 32 > /proc/gpufreqv2/fix_target_opp_index

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%21))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

	echo "fix_opp = $fix_opp"
	
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e khz

done
