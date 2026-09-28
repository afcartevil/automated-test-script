#!/system/bin/sh

#### ORDER or RANDOM
RANDOM_STRESS=1

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.02

echo " ***** STARTING DVFS STRESS ***** "

## MMDVFS MUST keep lowest voltage (for mt6989), need double setting.
echo 0 4 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

## Fixed UFS  vcore low requirement
echo 3 > /sys/devices/platform/soc/112b0000.ufshci/clkscale/clkscale_control

## Disable iSE##
echo disable 1 > /proc/ise

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%29))
	fix_opp=$(($fix_opp))
	
##	#need vcore >= 0.60v for 120HZ mmclk
##	if [ $fix_opp -eq 29 -o $fix_opp -eq 24 -o $fix_opp -eq 19 ]; then

##  dram >= 800M for 120HZ mmclk
##	if [ $fix_opp -ge 29 ]; then
##		continue
##	fi
	
	echo $fix_opp > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp

	echo "fix_opp = $fix_opp"
	
	cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps

done
