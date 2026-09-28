#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.02

echo " ***** STARTING DVFS STRESS ***** "

## MMDVFS MUST keep lowest voltage (for mt6993), need double setting.
echo 0 5 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

## Fixed UFS  vcore low requirement
echo 3 > /sys/devices/platform/soc/16810000.ufshci/clkscale/clkscale_control
echo 3 > /sys/devices/platform/soc/16890000.ufshci/clkscale/clkscale_control

## force HW-ZRAM vcore low requirement"
echo 3 > /sys/module/mtk_hwz/parameters/kick_hwe_gear

## Disable iSE is not need, iSE powered by vcore_sram
## echo disable 1 > /proc/ise

## unlock vcore dvfs setting
## echo 9595 > /sys/kernel/helio-dvfsrc/dvfsrc_force_ddr_opp

echo "fastest switching speed vcore dvfs stress, don't show OPP information"

while [ 1 ]
do
	## not sleep, fastest switching speed, from DX4 lesson learnt.
	## sleep $T_DVFS_INTERVAL

	fix_opp=$(($RANDOM%93))
	fix_opp=$(($fix_opp))
	
##	#need vcore >= 0.60v for 120HZ mmclk
##	if [ $fix_opp -eq 29 -o $fix_opp -eq 24 -o $fix_opp -eq 19 ]; then

##  dram >= 800M for 120HZ mmclk
##	if [ $fix_opp -ge 29 ]; then
##		continue
##	fi

##  force vcore >= 725mv
##	if [ $fix_opp -ge 101 ]; then
##		continue
##	fi

##	if [ $fix_opp -ge 80 -a $fix_opp -le 85 ]; then
##		continue
##	fi

##	if [ $fix_opp -ge 59 -a $fix_opp -le 64 ]; then
##		continue
##	fi

##	if [ $fix_opp -eq 41 -o $fix_opp -eq 42 -o $fix_opp -eq 43 -o $fix_opp -eq 28 ]; then
##		continue
##	fi

	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

##	echo "fix_opp = $fix_opp"
	
##	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps

done
