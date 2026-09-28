adb -s %1 push mm_dvfs_stress.sh /data/mm_dvfs_stress.sh
adb -s %1 shell chmod 777 /data/mm_dvfs_stress.sh
adb -s %1 shell sh /data/mm_dvfs_stress.sh