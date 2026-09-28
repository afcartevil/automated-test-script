#!/system/bin/sh

## monitor thermal change interval.
T_DVFS_INTERVAL=1

## thermal limit interval
HIGH_TEMP_LIMIT=95
LOW_TEMP_LIMIT=85

## high and low dram freq switch.
HIGH_VCORE_DVFS_OPP=0
LOW_VCORE_DVFS_OPP=71

## next need update high or low opp in thermal interval
NEXT_NEED_OPP=$HIGH_VCORE_DVFS_OPP

## last setting opp, default low opp.
LAST_SET_OPP=$LOW_VCORE_DVFS_OPP

echo "VCORE DVFS force high OPP($HIGH_VCORE_DVFS_OPP) Stress, thermal interval [$LOW_TEMP_LIMIT 'c - $HIGH_TEMP_LIMIT 'c], low opp($LOW_VCORE_DVFS_OPP)"

## MMDVFS MUST keep lowest voltage (for mt6993), need double setting.
echo 0 5 > /sys/module/mtk_mmdvfs_debug/parameters/force_step

## Fixed UFS  vcore low requirement
echo 3 > /sys/devices/platform/soc/16810000.ufshci/clkscale/clkscale_control
echo 3 > /sys/devices/platform/soc/16890000.ufshci/clkscale/clkscale_control

## force HW-ZRAM vcore low requirement
echo 3 > /sys/module/mtk_hwz/parameters/kick_hwe_gear

function get_max_temp() {
    max_temp=-273000
    # scan all thermal_zone
    for zone in /sys/class/thermal/thermal_zone*/temp; do
        # read the zone sensor data, and check return if error or not.
        current_temp=$(cat $zone 2>/dev/null)
		if [ $? -eq 0 ]; then
			current_temp=$(($current_temp))
			# compare the result.
			if [ $current_temp -gt $max_temp -a $current_temp -ne 125000 ]; then
				max_temp=$current_temp
			fi
		fi
    done
    # show the result.
    echo $(($max_temp/1000))
}

while [ 1 ]
do
	CURRENT_TEMP=$(get_max_temp)
	CURRENT_TEMP=$(($CURRENT_TEMP))

	if [ $CURRENT_TEMP -ge $HIGH_TEMP_LIMIT ]; then
		NEXT_NEED_OPP=$LOW_VCORE_DVFS_OPP
	elif [ $CURRENT_TEMP -ge $LOW_TEMP_LIMIT ]; then  ##temp from high to low, or low to high, don't change.
		NEXT_NEED_OPP=$LAST_SET_OPP                   ##Redundant, just to circumvent the syntax constraints of the shell
	else
		NEXT_NEED_OPP=$HIGH_VCORE_DVFS_OPP
	fi
	
	if [ $LAST_SET_OPP -ne $NEXT_NEED_OPP ]; then
		echo $NEXT_NEED_OPP > /sys/kernel/helio-dvfsrc/dvfsrc_force_vcore_dvfs_opp
		echo "fix_opp = $NEXT_NEED_OPP, current temp is $CURRENT_TEMP 'c"
		cat /sys/kernel/helio-dvfsrc/dvfsrc_dump | grep -e uv -e Mbps
		LAST_SET_OPP=$NEXT_NEED_OPP
	fi
	
	echo "Current temp is $CURRENT_TEMP 'c, Current OPP is $LAST_SET_OPP, sleep $T_DVFS_INTERVAL s"
	
	sleep $T_DVFS_INTERVAL

done