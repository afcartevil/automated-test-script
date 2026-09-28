#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.05

echo " ***** STARTING DVFS STRESS ***** "

#MMDVFS MUST keep lowest voltage (for mt6983)
echo 4 > /sys/module/mtk_mmdvfs/parameters/force_step

##Fix GPU  vcore low requirement£¬vgpu-vcore co-buck.
echo 32 > /proc/gpufreqv2/fix_target_opp_index
echo min > /proc/gpufreqv2/fix_target_opp_index

#Disable hold vcore whenever UFS access storage
#mt6983 NOT need setting.
#echo 0 > /proc/ufs_perf

#Let SCP in low freq, mt6983, SCP/SSPM/SPM eat vlp buck.
#echo opp 0 > /proc/scp_dvfs/scp_dvfs_ctrl

#Let fix APU vcore low requirement
echo 3 5 5 5 5 > /sys/module/apu_top/parameters/aputop_func_sel

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%27))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

	echo "fix_opp = $fix_opp"
	
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e khz

done
