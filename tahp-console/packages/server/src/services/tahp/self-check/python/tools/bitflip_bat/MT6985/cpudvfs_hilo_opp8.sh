#!/system/bin/sh

# read the cpu hvfs table from /proc/cpuhvfs/C{x}_opp_idx
C0_FILENAME='/proc/cpuhvfs/C0_opp_idx'
C1_FILENAME='/proc/cpuhvfs/C1_opp_idx'
C2_FILENAME='/proc/cpuhvfs/C2_opp_idx'
C3_FILENAME='/proc/cpuhvfs/C3_opp_idx'

c0_dvfs_table=()
c1_dvfs_table=()
c2_dvfs_table=()

c0_length=0
c1_length=0
c2_length=0

L_policy=0 #C0, Cluster0
BL_policy=4 #C1, Cluster1
B_policy=7 #C2, Cluster2

have_big_core=0

## keep screen always on
setprop persist.keep.awake true

if test -f $C3_FILENAME; then
	have_big_core=1
	echo "platform have big core."
fi

IFS=$'\n'
echo "cluster L cpu sign-off dvfs table"
for line in $(cat $C0_FILENAME)
do
	echo $line
	### please check the table to check how to substring.
	c0_dvfs_table[$c0_length]=${line#*'('}
	c0_dvfs_table[$c0_length]=${c0_dvfs_table[$c0_length]%','*}
#	echo ${c0_dvfs_table[$c0_length]}
	c0_length=$(($c0_length+1))
done

echo "cluster BL cpu sign-off dvfs table"
for line in $(cat $C1_FILENAME)
do
	echo $line
	### please check the table to check how to substring.
	c1_dvfs_table[$c1_length]=${line#*'('}
	c1_dvfs_table[$c1_length]=${c1_dvfs_table[$c1_length]%','*}
#	echo ${c1_dvfs_table[$c1_length]}
	c1_length=$(($c1_length+1))
done

if [ $have_big_core -eq 1 ]; then
	echo "cluster 2 cpu sign-off dvfs table"
	for line in $(cat $C2_FILENAME)
	do
		echo $line
		### please check the table to check how to substring.
		c2_dvfs_table[$c2_length]=${line#*'('}
		c2_dvfs_table[$c2_length]=${c2_dvfs_table[$c2_length]%','*}
	#	echo ${c2_dvfs_table[$c2_length]}
		c2_length=$(($c2_length+1))
	done
fi

L_ropp=$(($c0_length/2))
BL_ropp=$(($c1_length/2))
B_ropp=$(($c2_length/2))
L_freq=0
BL_freq=0
B_freq=0

L_freq=${c0_dvfs_table[$L_ropp]}
BL_freq=${c1_dvfs_table[$BL_ropp]}
if [ $have_big_core -eq 1 ]; then
	B_freq=${c2_dvfs_table[$B_ropp]}
fi
	
echo ${L_policy} ${L_freq} ${L_freq} > /proc/cpuhvfs/cpufreq_debug
echo ${BL_policy} ${BL_freq} ${BL_freq} > /proc/cpuhvfs/cpufreq_debug
if [ $have_big_core -eq 1 ]; then
	echo ${B_policy} ${B_freq} ${B_freq} > /proc/cpuhvfs/cpufreq_debug
	echo "DVFS cpu=${L_policy} ${BL_policy} ${B_policy}, opp=${L_ropp} ${BL_ropp} ${B_ropp}, freq=${L_freq} ${BL_freq} ${B_freq}"
else
	echo "DVFS cpu=${L_policy} ${BL_policy}, opp=${L_ropp} ${BL_ropp}, freq=${L_freq} ${BL_freq}"
fi

setprop persist.keep.awake false

echo "The test is done and PASS if no exception occurred."