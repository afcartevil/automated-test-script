adb -s %1 push gpu_dvfs_stress.sh /data/gpu_dvfs_sterss.sh
adb -s %1 shell chmod 755 /data/gpu_dvfs_sterss.sh
adb -s %1 shell sh /data/gpu_dvfs_sterss.sh