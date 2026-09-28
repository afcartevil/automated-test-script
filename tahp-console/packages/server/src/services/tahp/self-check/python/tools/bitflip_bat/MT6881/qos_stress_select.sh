#!/system/bin/sh

## ORDER or RANDOM
RANDOM_STRESS=1

## wait latency for each DVFS finish (0.1=100ms, 0.001=1ms), Switch slowly.
T_DVFS_INTERVAL=0.02

## so many opp need test, we select critical case to test
## select rule: min vcore, max dram freq, max emi freq
## for 6400Mbps HE/LP @ same voltage,  we select 6400Mbps wck low power mode(NOT Wck always on).
STRESS_OPP_LIST=(26 21 16 11 7 4 2 0)

echo STARTING DVFS STRESS with ${STRESS_OPP_LIST[@]}

#MMDVFS MUST keep lowest voltage (for mt6881), need double setting.
echo 4 > /sys/module/mtk_mmdvfs/parameters/force_step
echo 0 4 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

while [ 1 ]
do	
	sleep $T_DVFS_INTERVAL

	fix_index=$(($RANDOM%${#STRESS_OPP_LIST[@]}))
	fix_opp=${STRESS_OPP_LIST[$fix_index]}
	
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp
	echo "fix_opp = $fix_opp, fix_index=$fix_index" 
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps

done
