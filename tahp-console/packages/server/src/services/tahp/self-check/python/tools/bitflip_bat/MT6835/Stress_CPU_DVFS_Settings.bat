adb -s %1 push cpudvfs_hilo_test.sh /data/
adb -s %1 shell chmod 777 /data/cpudvfs*.sh
adb -s %1 shell sh /data/cpudvfs_hilo_test.sh