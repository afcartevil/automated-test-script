#!/system/bin/sh

## ORDER or RANDOM
RANDOM_STRESS=1

## wait latency for each DVFS finish (0.1=100ms, 0.001=1ms), Switch slowly.
T_DVFS_INTERVAL=0.02

## so many opp need test, we select critical case to test
## select rule: min vcore, max dram freq, max emi freq
## for 6400Mbps HE/LP @ same voltage,  we select 6400Mbps wck low power mode(NOT Wck always on).
### STRESS_OPP_LIST=(12 3 0)
STRESS_OPP_LIST=(108 87 66 45 30 20 14 8 5 2 1 0)

echo STARTING DVFS STRESS with ${STRESS_OPP_LIST[@]}

## MMDVFS MUST keep lowest voltage (for mt6993), need double setting.
echo 0 5 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

## Fixed UFS  vcore low requirement
echo 3 > /sys/devices/platform/soc/16810000.ufshci/clkscale/clkscale_control

##  Fixed GPS  vcore low requirement, only a0/es1
settings put secure location_mode 0

## Disable iSE is not need, iSE powered by vcore_sram
## echo disable 1 > /proc/ise

## unlock vcore dvfs setting
## echo 9595 > /sys/kernel/helio-dvfsrc/dvfsrc_force_ddr_opp

while [ 1 ]
do	
	sleep $T_DVFS_INTERVAL

	fix_index=$(($RANDOM%${#STRESS_OPP_LIST[@]}))
	fix_opp=${STRESS_OPP_LIST[$fix_index]}
	
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp
	echo "fix_opp = $fix_opp, fix_index=$fix_index" 
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps

done
