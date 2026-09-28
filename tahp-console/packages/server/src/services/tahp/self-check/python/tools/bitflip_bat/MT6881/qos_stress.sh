#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.05

echo " ***** STARTING DVFS STRESS ***** "

#MMDVFS MUST keep lowest voltage (for mt6881), need double setting.
echo 4 > /sys/module/mtk_mmdvfs/parameters/force_step
echo 0 4 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

while [ 1 ]
do
	## not sleep, fastest switching speed, from DX4 lesson learnt.
	## sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%27))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

	echo "fix_opp = $fix_opp"
	
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e khz

done
