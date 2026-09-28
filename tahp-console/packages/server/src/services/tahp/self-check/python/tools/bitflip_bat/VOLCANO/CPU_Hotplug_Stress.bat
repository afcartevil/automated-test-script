:: Qualcomm volcano: start device-side cpu hotplug toggle loop in background
:: %~dp0 makes the push work regardless of caller's cwd; loop dies on next reboot
adb -s %1 push %~dp0cpu_hotplug_loop.sh /data/local/tmp/cpu_hotplug_loop.sh
adb -s %1 shell chmod 755 /data/local/tmp/cpu_hotplug_loop.sh
adb -s %1 shell "nohup sh /data/local/tmp/cpu_hotplug_loop.sh > /data/local/tmp/hotplug_loop.txt 2>&1 &"
