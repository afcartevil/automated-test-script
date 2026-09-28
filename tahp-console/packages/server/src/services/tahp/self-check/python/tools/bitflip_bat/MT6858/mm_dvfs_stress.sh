#!/system/bin/sh

#### wait latency for each DVFS finish (0.1=100ms, 0.001=1ms)
T_DVFS_INTERVAL=0.2

echo "dump default setting."

cat /sys/module/mtk_mmdvfs/parameters/dump_setting

echo 0 > /sys/module/mtk_mmdvfs/parameters/force_step
echo 0 0 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

echo " ***** STARTING DVFS STRESS ***** "

while [ 1 ]
do
	sleep $T_DVFS_INTERVAL
	
	fix_opp=$(($RANDOM%4))
	fix_opp=$(($fix_opp))
	echo $fix_opp > /sys/module/mtk_mmdvfs/parameters/force_step
	echo 0 $fix_opp > /sys/module/mtk_mmdvfs_debug/parameters/force_step

	echo "fix_opp = $fix_opp"
	
	cat /sys/module/mtk_mmdvfs/parameters/dump_setting | grep -e force -e request -e vote

done
