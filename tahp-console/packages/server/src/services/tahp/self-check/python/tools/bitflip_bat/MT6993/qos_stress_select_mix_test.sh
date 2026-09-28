#!/system/bin/sh

## ORDER or RANDOM
RANDOM_STRESS=1

## wait latency for each DVFS finish (0.1=100ms, 0.001=1ms), Switch slowly.
T_DVFS_INTERVAL_HIGH=5
T_DVFS_INTERVAL_LOW=5

## High and low dram freq switch.
HIGH_VCORE_DVFS_OPP=0
LOW_VCORE_DVFS_OPP=71

echo "VCORE DVFS High OPP=$HIGH_VCORE_DVFS_OPP($T_DVFS_INTERVAL_HIGH s) and Low OPPO=$LOW_VCORE_DVFS_OPP($T_DVFS_INTERVAL_LOW s) switch" 

## MMDVFS MUST keep lowest voltage (for mt6993), need double setting.
echo 0 5 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

## Fixed UFS  vcore low requirement
echo 3 > /sys/devices/platform/soc/16810000.ufshci/clkscale/clkscale_control
echo 3 > /sys/devices/platform/soc/16890000.ufshci/clkscale/clkscale_control

## force HW-ZRAM vcore low requirement"
echo 3 > /sys/module/mtk_hwz/parameters/kick_hwe_gear

while [ 1 ]
do		
	echo $HIGH_VCORE_DVFS_OPP > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp
	echo "fix_opp = $HIGH_VCORE_DVFS_OPP, sleep=$T_DVFS_INTERVAL_HIGH s" 
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps
	
	sleep $T_DVFS_INTERVAL_HIGH
	
	echo $LOW_VCORE_DVFS_OPP > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp
	echo "fix_opp = $LOW_VCORE_DVFS_OPP, sleep=$T_DVFS_INTERVAL_LOW s"
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps
	
	sleep $T_DVFS_INTERVAL_LOW

done
