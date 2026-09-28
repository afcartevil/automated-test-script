#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.05

echo " ***** STARTING DVFS STRESS ***** "

#MMDVFS MUST keep lowest voltage (for mt6985)
echo 0 4 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

#Let SCP in low freq, mt6983, SCP/SSPM/SPM eat vlp buck.
#echo opp 0 > /proc/scp_dvfs/scp_dvfs_ctrl

#Let fix APU vcore low requirement
echo 3 5 5 5 5 > /sys/module/apu_top/parameters/aputop_func_sel

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%29))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

	echo "fix_opp = $fix_opp"
	
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e khz

done
