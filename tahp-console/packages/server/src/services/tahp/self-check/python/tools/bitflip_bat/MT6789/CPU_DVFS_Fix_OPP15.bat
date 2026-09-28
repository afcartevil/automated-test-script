echo "avoid thermal reboot, we reduce the frequency every once in a while"
adb -s %1 push cpudvfs_hilo_opp15.sh /data/
adb -s %1 shell chmod 755 /data/cpudvfs*.sh
adb -s %1 shell sh /data/cpudvfs_hilo_opp15.sh