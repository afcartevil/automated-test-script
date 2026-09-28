adb -s %1 push cpuhotplug_hilo_test.sh /data/
adb -s %1 shell chmod 777 /data/cpuhotplug_hilo_test.sh
adb -s %1 shell sh /data/cpuhotplug_hilo_test.sh